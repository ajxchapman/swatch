import unittest

from src.selector import Selector, SelectorItem


class TestSelectorItemClone(unittest.TestCase):
    def test_clone_preserves_empty_value(self):
        # Regression: clone used `value or self.value`, so an explicit empty
        # result was silently replaced by the original value.
        item = SelectorItem(b'original', vars={"k": b"v"})
        cloned = item.clone(b'')
        self.assertEqual(cloned.value, b'')
        # vars are carried over
        self.assertEqual(cloned.vars, {"k": b"v"})

    def test_clone_none_keeps_value(self):
        item = SelectorItem(b'original')
        cloned = item.clone()
        self.assertEqual(cloned.value, b'original')

    def test_clone_merges_vars(self):
        item = SelectorItem(b'x', vars={"a": b"1"})
        cloned = item.clone(vars={"b": b"2"})
        self.assertEqual(cloned.vars, {"a": b"1", "b": b"2"})


class TestSelectorEmptyResults(unittest.TestCase):
    def setUp(self) -> None:
        from src.context import Context
        self.ctx = Context()

    def test_split_keeps_empty_fields(self):
        s: Selector = Selector.load(type="split", sep=",")
        result = s.run(self.ctx, SelectorItem(b'a,,b'))
        self.assertListEqual([x.value for x in result], [b'a', b'', b'b'])

    def test_strip_to_empty(self):
        s: Selector = Selector.load(type="strip")
        result = s.run(self.ctx, SelectorItem(b'   '))
        self.assertEqual(result[0].value, b'')

    def test_replace_to_empty(self):
        s: Selector = Selector.load(type="replace", regex="abc", replacement="")
        result = s.run(self.ctx, SelectorItem(b'abc'))
        self.assertEqual(result[0].value, b'')

    def test_lines_keeps_blank_lines(self):
        s: Selector = Selector.load(type="lines")
        result = s.run(self.ctx, SelectorItem(b'a\n\nb'))
        self.assertListEqual([x.value for x in result], [b'a', b'', b'b'])
