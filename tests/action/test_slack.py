import unittest

from src.action import Action
from src.context import Context


def make(**kw):
    return Action.load(**{"type": "slack", "url": "http://example/hook", **kw})


class TestSlackChunking(unittest.TestCase):
    def test_short_message_single_chunk(self):
        s = make()
        msg = "one\ntwo\nthree"
        self.assertListEqual(s.chunk(msg), [msg])

    def test_splits_on_newline_under_limit(self):
        s = make(max_length=25)
        lines = [f"line-{i:03d}" for i in range(20)]  # 8 chars each
        msg = "\n".join(lines)
        chunks = s.chunk(msg)
        # Every chunk is within the limit and made of whole lines
        self.assertTrue(all(len(c) <= 25 for c in chunks))
        for c in chunks:
            for line in c.split("\n"):
                self.assertIn(line, lines)
        # No data lost, order preserved, split only on newlines
        self.assertEqual("\n".join(chunks), msg)

    def test_never_splits_within_a_line(self):
        s = make(max_length=40)
        msg = "\n".join([f"* item {i} <https://crbug.com/48665748{i}|link>" for i in range(10)])
        for c in s.chunk(msg):
            # each chunk rejoins to whole lines only
            for line in c.split("\n"):
                self.assertTrue(line.startswith("* item ") and line.endswith("|link>"))

    def test_long_single_line_emitted_whole(self):
        s = make(max_length=10)
        long = "x" * 50
        self.assertListEqual(s.chunk(f"{long}\nshort"), [long, "short"])

    def test_empty_message_no_chunks(self):
        s = make()
        self.assertListEqual(s.chunk(""), [])
        self.assertListEqual(s.chunk(None), [])

    def test_run_posts_each_chunk_in_order(self):
        s = make(max_length=25)
        sent = []
        s.post = lambda message: sent.append(message)
        msg = "\n".join([f"line-{i:03d}" for i in range(20)])
        s.run(msg)
        self.assertGreater(len(sent), 1)          # actually chunked
        self.assertEqual("\n".join(sent), msg)     # order + integrity preserved

    def test_report_and_error_route_through_run(self):
        s = make(max_length=25)
        sent = []
        s.post = lambda message: sent.append(message)
        ctx = Context()
        s.report(ctx, {"comment": "a\nb\nc"})
        s.error(ctx, {"error": "e1\ne2"})
        self.assertEqual(sent, ["a\nb\nc", "e1\ne2"])
