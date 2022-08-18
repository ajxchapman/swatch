import unittest

from src.watch import Watch, Context


class TestConditionalWatch(unittest.TestCase):
    def test_success_success(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "true"}
        }, then={
            "type": "count",
            "match" : {"type" : "true"}
        })
        
        ctx = Context()
        result = w.process(ctx)
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
        
        ctx = Context()
        result = w.process(ctx)
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
        
        ctx = Context()
        result = w.process(ctx)
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
        
        ctx = Context()
        result = w.process(ctx)
        self.assertEqual(result, False)
        self.assertEqual(w.conditional.group[0].count, 1)
        self.assertEqual(w.then.count, 0)