import logging
import typing
import unittest

from src.action import Action
from src.cache import Cache
from src.context import Context
from src.watch import Watch


class BoomAction(Action):
    def report(self, ctx: Context, data: dict) -> None:
        raise RuntimeError("boom")

    def error(self, ctx: Context, data: dict) -> None:
        raise RuntimeError("boom")


class RecordAction(Action):
    reported: typing.List[dict] = []

    def report(self, ctx: Context, data: dict) -> None:
        RecordAction.reported.append(data)


class TestActionIsolation(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
        self.ctx.set_variable("watch_file", "test.yml")
        RecordAction.reported = []
        logging.getLogger("src.watch").setLevel(logging.CRITICAL)

    def tearDown(self) -> None:
        logging.getLogger("src.watch").setLevel(logging.NOTSET)
        self.cache.close()

    def test_failing_action_does_not_abort_others(self):
        # A failing report action must not prevent subsequent actions from
        # running or crash the whole execute() call.
        self.ctx.set_variable("config", {})
        w = Watch.load(
            type="true",
            match={"type": "true"},
            actions=[{"type": "boom"}, {"type": "record"}],
            action_data={"value": "x"},
        )
        # Should not raise despite the boom action
        w.execute(self.ctx)
        self.assertEqual(len(RecordAction.reported), 1)
