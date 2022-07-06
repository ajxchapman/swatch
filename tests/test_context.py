import unittest

from src.context import Context

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
