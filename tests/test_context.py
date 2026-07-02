import unittest

from src.context import Context, ContextException

class TestContextFrames(unittest.TestCase):
    def test_push_pop_variable(self):
        ctx = Context()
        ctx.push_frame("frame")
        ctx.push_variable("k", "v1")
        ctx.push_variable("k", "v2")
        self.assertEqual(ctx.get_variable("k"), "v2")
        self.assertEqual(ctx.pop_variable("k"), "v2")
        self.assertEqual(ctx.get_variable("k"), "v1")
        self.assertEqual(ctx.pop_variable("k"), "v1")
        # Once emptied the key is removed from the frame
        self.assertIsNone(ctx.get_variable("k"))
        ctx.pop_frame("frame")

    def test_pop_frame_mismatch(self):
        # Regression: a frame id mismatch should raise a clean ContextException
        # rather than a KeyError from referencing a non-existent frame key.
        ctx = Context()
        ctx.push_frame("expected")
        with self.assertRaises(ContextException):
            ctx.pop_frame("wrong")

    def test_get_variable_returns_most_recent_frame(self):
        # Regression: get_variable iterated outermost-first, returning the
        # shallowest frame's value instead of the most recently pushed one.
        ctx = Context()
        ctx.push_frame("A")
        ctx.push_variable("hash", "A")
        ctx.push_frame("B")
        ctx.push_variable("hash", "B")
        self.assertEqual(ctx.get_variable("hash"), "B")
        ctx.pop_variable("hash")
        ctx.pop_frame("B")
        # Falls back to the outer frame once the inner value is gone
        self.assertEqual(ctx.get_variable("hash"), "A")

    def test_frameid_not_exposed(self):
        # The internal `_frameId` bookkeeping key must not leak as a variable
        ctx = Context()
        ctx.push_frame("A")
        self.assertNotIn("_frameId", ctx.keys())
        self.assertIsNone(ctx.get_variable("_frameId"))

class TestContext(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.ctx.set_variable("STR", "123")
        self.ctx.set_variable("BYTES", b'123')
        self.ctx.set_variable("INT", 123)
        self.ctx.set_variable("NONE", None)
        self.ctx.set_variable("ARRAY0", [])
        self.ctx.set_variable("ARRAY1", ["123"])
        self.ctx.set_variable("ARRAY2", ["123", "456"])
        self.ctx.set_variable("DICT0", {})
        self.ctx.set_variable("DICT1", {"STR" : "123"})

    def test_expand_str(self):
        self.assertEqual(self.ctx.expand_context("aaabbb"), "aaabbb")
        self.assertEqual(self.ctx.expand_context("aaa{{STR}}bbb"), "aaa123bbb")
        self.assertEqual(self.ctx.expand_context("aaa{{BYTES}}bbb"), "aaa123bbb")
        self.assertEqual(self.ctx.expand_context("aaa{{INT}}bbb"), "aaa123bbb")
        self.assertEqual(self.ctx.expand_context("aaa{{NONE}}bbb"), "aaabbb")

        self.assertEqual(self.ctx.expand_context("aaa{{ARRAY0}}bbb"), "aaabbb")
        self.assertEqual(self.ctx.expand_context("aaa{{ARRAY1}}bbb"), "aaa123bbb")
        self.assertEqual(self.ctx.expand_context("aaa{{ARRAY2}}bbb"), "aaa['123', '456']bbb")

        self.assertEqual(self.ctx.expand_context("aaa{{DICT0}}bbb"), "aaabbb")
        self.assertEqual(self.ctx.expand_context("aaa{{DICT1}}bbb"), "aaa{'STR': '123'}bbb")
        self.assertEqual(self.ctx.expand_context("aaa{{DICT1.STR}}bbb"), "aaa123bbb")
        self.assertEqual(self.ctx.expand_context("aaa{{DICT1.DOES_NOT_EXIST}}bbb"), "aaabbb")

        self.assertEqual(self.ctx.expand_context("aaa{{DOES_NOT_EXIST}}bbb"), "aaabbb")
        self.assertEqual(self.ctx.expand_context("aaa{{DOES_NOT_EXIST | default('123')}}bbb"), "aaa123bbb")

    def test_expand_list(self):
        self.assertListEqual(self.ctx.expand_context(["aaabbb", 123, "xx"]), ["aaabbb", 123, "xx"])
        self.assertListEqual(self.ctx.expand_context(["aaa{{STR}}bbb", 123, "xx"]), ["aaa123bbb", 123, "xx"])
        self.assertListEqual(self.ctx.expand_context(["aaabbb", 123, "x{{STR}}x"]), ["aaabbb", 123, "x123x"])


    def test_expand_dict(self):
        self.assertDictEqual(self.ctx.expand_context({"aa" : "bb", "cc" : "dd", "ee" : "ff"}), {"aa" : "bb", "cc" : "dd", "ee" : "ff"})
        self.assertDictEqual(self.ctx.expand_context({"a{{STR}}a" : "bb", "cc" : "dd", "ee" : "ff"}), {"a123a" : "bb", "cc" : "dd", "ee" : "ff"})
        self.assertDictEqual(self.ctx.expand_context({"aa" : "b{{STR}}b", "cc" : "dd", "ee" : "ff"}), {"aa" : "b123b", "cc" : "dd", "ee" : "ff"})
        self.assertDictEqual(self.ctx.expand_context({"aa" : "bb", "cc" : "dd", "e{{STR}}e" : "ff"}), {"aa" : "bb", "cc" : "dd", "e123e" : "ff"})
        self.assertDictEqual(self.ctx.expand_context({"aa" : "bb", "cc" : "dd", "ee" : "f{{STR}}f"}), {"aa" : "bb", "cc" : "dd", "ee" : "f123f"})
