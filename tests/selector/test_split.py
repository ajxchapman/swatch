import unittest

from src.context import Context
from src.selector import Selector

class TestSplitSelector(unittest.TestCase):
    def test_1(self):
        s: Selector = Selector.load(type="split", sep=",")
        data = b'1,2,3,4'

        ctx = Context()
        result = s.run(ctx, data)
        self.assertEqual(len(result), 4)
