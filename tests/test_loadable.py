import unittest

from src.loadable import Loadable, LoadableException

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

class Hash(Loadable):
    keys = {
        "value" : (lambda x: x, None),
        "comment" : (str, None)
    }
    hash_skip = ["comment"]

class BaseHash(Hash):
    pass


class TypeTest(Loadable):
    keys = {
        "before" : (str, "before")
    }
    type_determination_skip = ["before"]

class SubTypeTest(TypeTest):
    keys = {
        "sub" : (str, "123")
    }
    

class TestLoadable(unittest.TestCase):
    def test_1(self):
        o = Loadable1.load(type="Base1", key5=5, key6="6")
        self.assertEqual(o.key1, "value1")
        self.assertEqual(o.key2, "value2")
        self.assertEqual(o.key3, "overridden3")
        self.assertEqual(o.key4, "value4")
        self.assertEqual(o.key5, "5")
        self.assertEqual(o.key6, 6)
        self.assertEqual(o.key7, "value7")

    def test_unknown(self):
        o = Hash.load(type="base", value=123, unknown=456)
        self.assertRaises(AttributeError, lambda: o.unknown)
        self.assertEqual(o.kwargs["unknown"], 456)
        
    def test_hash(self):
        s = Hash.load(type="base", value=123)
        o = Hash.load(type="base", value=123)
        self.assertEqual(s.hash, o.hash)

        s = Hash.load(type="base", value=123)
        o = Hash.load(type="base", value=123, comment="comment")
        self.assertEqual(o.comment, "comment")
        self.assertEqual(s.hash, o.hash)
        
        s = Hash.load(type="base", value={1 : 2})
        o = Hash.load(type="base", value={1 : 2, "comment" : "comment"})
        self.assertEqual(o.value["comment"], "comment")
        self.assertEqual(s.hash, o.hash)

        s = Hash.load(type="base", value={1 : {2 : 3}})
        o = Hash.load(type="base", value={1 : {2 : 3, "comment" : "comment"}})
        self.assertEqual(o.value[1]["comment"], "comment")
        self.assertEqual(s.hash, o.hash)

        s = Hash.load(type="base", value=[1, 2, 3, {}])
        o = Hash.load(type="base", value=[1, 2, 3, {"comment" : "comment"}])
        self.assertEqual(o.value[3]["comment"], "comment")
        self.assertEqual(s.hash, o.hash)

        s = Hash.load(type="base", value=[1, {2 : 3}])
        o = Hash.load(type="base", value=[1, {2 : 3, "comment" : "comment"}])
        self.assertEqual(o.value[1]["comment"], "comment")
        self.assertEqual(s.hash, o.hash)

    def test_load_defined(self):
        o = TypeTest.load(**{"type": "sub"})
        self.assertEqual(o.__class__, SubTypeTest)
        self.assertEqual(o.sub, "123")
        
    def test_load_determined(self):
        o = TypeTest.load(**{"sub" : "456"})
        self.assertEqual(o.__class__, SubTypeTest)
        self.assertEqual(o.sub, "456")

    def test_gettype_determined_exception(self):
        with self.assertRaises(LoadableException):
            TypeTest.load(**{"after" : "789", "sub" : "456"})

    def test_gettype_determined_skip(self):
        o = TypeTest.load(**{"before" : "789", "sub" : "456"})
        self.assertEqual(o.__class__, SubTypeTest)
        self.assertEqual(o.sub, "456")
        self.assertEqual(o.before, "789")
