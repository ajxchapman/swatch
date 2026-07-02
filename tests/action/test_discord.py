import json
import unittest

import src.action as action_module
from src.action import Action
from src.context import Context


class TestDiscordAction(unittest.TestCase):
    def setUp(self) -> None:
        self.sent = []
        self._orig = action_module.requests.request
        action_module.requests.request = lambda method, url, headers, data: self.sent.append(json.loads(data))

    def tearDown(self) -> None:
        action_module.requests.request = self._orig

    def make(self, **kw):
        return Action.load(**{"type": "discord", "url": "http://discord/hook", **kw})

    def test_link_conversion(self):
        s = self.make()
        self.assertEqual(
            s.transform("see <https://crbug.com/1|crbug> now"),
            "see [crbug](https://crbug.com/1) now",
        )

    def test_multiple_links_and_bare_url_untouched(self):
        s = self.make()
        out = s.transform("(<https://a|x>, <https://b|y>) and https://bare.example/")
        self.assertEqual(out, "([x](https://a), [y](https://b)) and https://bare.example/")

    def test_default_payload_is_content(self):
        s = self.make()
        s.run("hello")
        self.assertListEqual(self.sent, [{"content": "hello"}])

    def test_run_converts_links_before_send(self):
        s = self.make()
        s.run("* item <https://crbug.com/486657483|crbug.com/486657483>")
        self.assertEqual(
            self.sent[0]["content"],
            "* item [crbug.com/486657483](https://crbug.com/486657483)",
        )

    def test_chunks_on_newline_under_2000(self):
        s = self.make()
        lines = [f"line-{i:04d}" for i in range(500)]  # ~5000 chars total
        s.run("\n".join(lines))
        self.assertGreater(len(self.sent), 1)
        for body in self.sent:
            self.assertLessEqual(len(body["content"]), 2000)
            for line in body["content"].split("\n"):
                self.assertIn(line, lines)
        # order + integrity preserved, split only on newlines
        self.assertEqual("\n".join(b["content"] for b in self.sent), "\n".join(lines))

    def test_report_and_error(self):
        s = self.make()
        ctx = Context()
        s.report(ctx, {"comment": "a\nb"})
        s.error(ctx, {"error": "boom"})
        self.assertListEqual(self.sent, [{"content": "a\nb"}, {"content": "boom"}])


class TestSlackUnaffected(unittest.TestCase):
    def test_slack_keeps_link_syntax(self):
        s = Action.load(type="slack", url="http://slack/hook")
        # Slack uses <url|text> natively -> transform must be identity
        self.assertEqual(s.transform("<https://x|y>"), "<https://x|y>")
