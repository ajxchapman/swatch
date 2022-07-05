import unittest

from src.selector import Selector

class TestSplitModifier(unittest.TestCase):
    def test_1(self):
        m = Selector.load(type="split", sep=",")
        data = b'1,2,3,4'
        result = m.run(data)
        self.assertEqual(len(result), 4)
