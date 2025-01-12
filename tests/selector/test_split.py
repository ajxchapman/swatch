import unittest

from src.context import Context
from src.selector import Selector, SelectorItem

class TestSplitSelector(unittest.TestCase):
    def test_1(self):
        s: Selector = Selector.load(type="split", sep=",")
        item = SelectorItem(b'1,2,3,4')

        ctx = Context()
        result = s.run(ctx, item)
        self.assertEqual(len(result), 4)

    def test_values(self):
        s: Selector = Selector.load(type="split", sep=",")
        item = SelectorItem(b'1,2,3,4', vars={"var1": "xxx"})

        ctx = Context()
        result = s.run(ctx, item)
        self.assertEqual(result[-1].vars, item.vars)
