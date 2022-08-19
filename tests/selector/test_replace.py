import unittest

from src.context import Context
from src.selector import Selector

class TestReplaceSelector(unittest.TestCase):
    def test_1(self):
        s: Selector = Selector.load(type="replace", regex=".*(AAbbCC).*", replacement="https://example.com/\\1")
        data = b'xxAAbbCCxx'

        ctx = Context()
        result = s.run(ctx, data)
        self.assertEqual(result[0], b'https://example.com/AAbbCC')
