import unittest

from watch import Modifier

class TestSplitModifier(unittest.TestCase):
    def test_1(self):
        m = Modifier.load(type="split", sep=",")
        data = b'1,2,3,4'
        result = m.run(data)
        self.assertEqual(len(result), 4)
