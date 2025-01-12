import unittest

from src.context import Context
from src.selector import Selector, SelectorItem

class TestStripSelector(unittest.TestCase):
    def test_1(self):
        s: Selector = Selector.load(type="strip")
        item = SelectorItem(b'\ntest\n')

        ctx = Context()
        result = s.run(ctx, item)
        self.assertEqual(result[0].value, b'test')
