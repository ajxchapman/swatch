import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch


class TestOnceWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
        self.ctx.set_variable("templates", {
            "count" : {
                "type" : "count",
                "match" : {"type" : "true"}
            },
            "static" : {
                "static": ["result {{ k1 }}"],
                "match" : {"type" : "true"}
            }
        })
    
    def tearDown(self) -> None:
        self.cache.close()

    def test_count(self):
        w = Watch.load(template="count")
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertEqual(w.subwatch.count, 1)

    def test_data(self):
        w = Watch.load(template="static", variables={"k1" : "v1"})
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertLessEqual(self.ctx.get_variable(w.subwatch.hash), ["result v1"])

    def test_hash(self):
        w1 = Watch.load(template="static", variables={"k1" : "v1"})
        w2 = Watch.load(template="static", variables={"k1" : "v2"})
        
        w1.process(self.ctx)
        w2.process(self.ctx)

        self.assertNotEqual(w1.hash, w2.hash)
        self.assertNotEqual(w1.subwatch.hash, w2.subwatch.hash)
