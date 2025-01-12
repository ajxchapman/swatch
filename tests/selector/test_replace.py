import unittest

from src.context import Context
from src.selector import Selector, SelectorItem

class TestReplaceSelector(unittest.TestCase):
    def test_1(self):
        s: Selector = Selector.load(type="replace", regex=".*(AAbbCC).*", replacement="https://example.com/\\1")
        item = SelectorItem(b'xxAAbbCCxx')

        ctx = Context()
        result = s.run(ctx, item)
        self.assertEqual(result[0].value, b'https://example.com/AAbbCC')
