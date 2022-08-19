import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch


class TestConditionalWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
    
    def tearDown(self) -> None:
        self.cache.close()

    def test_success_success(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "true"}
        }, then={
            "type": "count",
            "match" : {"type" : "true"}
        })
        
        result = w.process(self.ctx)
        self.assertEqual(result, True)
        self.assertEqual(w.conditional.group[0].count, 1)
        self.assertEqual(w.then.count, 1)

    def test_success_failure(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "true"}
        }, then={
            "type": "count",
            "match" : {"type" : "false"}
        })
        
        result = w.process(self.ctx)
        self.assertEqual(result, False)
        self.assertEqual(w.conditional.group[0].count, 1)
        self.assertEqual(w.then.count, 1)

    def test_failure_success(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "false"}
        }, then={
            "type": "count",
            "match" : {"type" : "true"}
        })
        
        result = w.process(self.ctx)
        self.assertEqual(result, False)
        self.assertEqual(w.conditional.group[0].count, 1)
        self.assertEqual(w.then.count, 0)
    
    def test_failure_failure(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "false"}
        }, then={
            "type": "count",
            "match" : {"type" : "false"}
        })
        
        result = w.process(self.ctx)
        self.assertEqual(result, False)
        self.assertEqual(w.conditional.group[0].count, 1)
        self.assertEqual(w.then.count, 0)