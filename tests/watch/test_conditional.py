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
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertEqual(w.conditional.watches[0].count, 1)
        self.assertEqual(w.subwatch.count, 1)

    def test_success_failure(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "true"}
        }, then={
            "type": "count",
            "match" : {"type" : "false"}
        })
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, False)
        self.assertEqual(w.conditional.watches[0].count, 1)
        self.assertEqual(w.subwatch.count, 1)

    def test_failure_success(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "false"}
        }, then={
            "type": "count",
            "match" : {"type" : "true"}
        })
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, False)
        self.assertEqual(w.conditional.watches[0].count, 1)
        self.assertEqual(w.subwatch.count, 0)
    
    def test_failure_failure(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "false"}
        }, then={
            "type": "count",
            "match" : {"type" : "false"}
        })
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, False)
        self.assertEqual(w.conditional.watches[0].count, 1)
        self.assertEqual(w.subwatch.count, 0)