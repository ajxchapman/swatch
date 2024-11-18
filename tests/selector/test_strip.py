import unittest

from src.context import Context
from src.selector import Selector

class TestStripSelector(unittest.TestCase):
    def test_1(self):
        s: Selector = Selector.load(type="strip")
        data = b'\ntest\n'

        ctx = Context()
        result = s.run(ctx, data)
        self.assertEqual(result[0], b'test')
