import unittest

from src.modifier import Modifier

class TestReplaceModifier(unittest.TestCase):
    def test_1(self):
        m = Modifier.load(type="replace", regex=".*(AAbbCC).*", replacement="https://example.com/\\1")
        data = b'xxAAbbCCxx'
        result = m.run(data)
        self.assertEqual(result[0], b'https://example.com/AAbbCC')
