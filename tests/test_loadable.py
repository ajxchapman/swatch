import unittest

from src.loadable import Loadable

class Loadable1(Loadable):
    keys = {
        "key1" : "value1",
        "key2" : (str, "value2"),
        "key3" : "value3",
    }

class Base1(Loadable1):
    keys = {
        "key3" : "overridden3",
        "key4" : "value4",
        "key5" : (str, "value5"),
        "key6" : (int, "value6"),
        "key7" : (int, "value7"),
    }

class TestReplaceModifier(unittest.TestCase):
    def test_1(self):
        o = Loadable1.load(type="Base1", key5=5, key6="6")
        self.assertEqual(o.key1, "value1")
        self.assertEqual(o.key2, "value2")
        self.assertEqual(o.key3, "overridden3")
        self.assertEqual(o.key4, "value4")
        self.assertEqual(o.key5, "5")
        self.assertEqual(o.key6, 6)
        self.assertEqual(o.key7, "value7")
        
