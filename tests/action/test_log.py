import logging
import unittest

from src.action import Action
from src.context import Context


class TestLogAction(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.action = Action.load(type="log")

    def test_report_comment(self):
        with self.assertLogs("src.action", level="INFO") as cm:
            self.action.report(self.ctx, {"comment": "hello\nworld", "data": []})
        self.assertTrue(any("hello" in m and "world" in m for m in cm.output))

    def test_report_empty_comment_with_data(self):
        # Regression: when the comment is empty the action fell back to the data
        # list and called .split() on it, raising AttributeError. `log` is a
        # default action, so this crashed reporting for any triggered watch
        # without a comment.
        data = {"comment": "", "data": [{"id": "x", "executed": 1}]}
        with self.assertLogs("src.action", level="INFO") as cm:
            self.action.report(self.ctx, data)
        self.assertTrue(any("id" in m for m in cm.output))

    def test_error(self):
        with self.assertLogs("src.action", level="ERROR") as cm:
            self.action.error(self.ctx, {"error": "boom"})
        self.assertTrue(any("boom" in m for m in cm.output))
