import unittest

from watch import Modifier

class TestReplaceModifier(unittest.TestCase):
    def test_1(self):
        m = Modifier.load(type="replace", regex=".*(AAbbCC).*", replacement="https://example.com/\\1")
        data = b'xxAAbbCCxx'
        result = m.run(data)
        print(result)
        self.assertEqual(len(result), 4)
