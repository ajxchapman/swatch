import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch

class TestGroupWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
    
    def tearDown(self) -> None:
        self.cache.close()

    def test_and_success(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"}
        }, {
            "type": "count",
            "match" : {"type" : "true"}
        }], operator="all")
        
        result = w.process(self.ctx)
        self.assertEqual(result, True)
        self.assertEqual(w.group[0].count, 1)
        self.assertEqual(w.group[1].count, 1)

    def test_and_failure(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "false"}
        }, {
            "type": "count",
            "match" : {"type" : "true"}
        }], operator="all")
        
        result = w.process(self.ctx)
        self.assertEqual(result, False)
        self.assertEqual(w.group[0].count, 1)
        self.assertEqual(w.group[1].count, 0) # Ensure early exit

    def test_or_success(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"}
        }, {
            "type": "count",
            "match" : {"type" : "false"}
        }], operator="any")
        
        result = w.process(self.ctx)
        self.assertEqual(result, True)
        self.assertEqual(w.group[0].count, 1)
        self.assertEqual(w.group[1].count, 1)

    def test_or_failure(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "false"}
        }, {
            "type": "count",
            "match" : {"type" : "false"}
        }], operator="any")
        
        result = w.process(self.ctx)
        self.assertEqual(result, False)
        self.assertEqual(w.group[0].count, 1)
        self.assertEqual(w.group[1].count, 1)

    def test_last_success(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "false"}
        }, {
            "type": "count",
            "match" : {"type" : "true"}
        }], operator="last")
        
        result = w.process(self.ctx)
        self.assertEqual(result, True)
        self.assertEqual(w.group[0].count, 1)
        self.assertEqual(w.group[1].count, 1)


    def test_last_failure(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"}
        }, {
            "type": "count",
            "match" : {"type" : "false"}
        }], operator="last")
        
        result = w.process(self.ctx)
        self.assertEqual(result, False)
        self.assertEqual(w.group[0].count, 1)
        self.assertEqual(w.group[1].count, 1)
