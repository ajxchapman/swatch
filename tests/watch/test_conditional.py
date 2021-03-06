import unittest

from src.watch import Watch, Context


class TestConditionalWatch(unittest.TestCase):
    def test_success(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "true"}
        }, then={
            "type": "count",
            "match" : {"type" : "true"}
        })
        
        ctx = Context()
        result = w.match_data(ctx, w.process_data(ctx))
        self.assertEqual(result, True)
        self.assertEqual(w.conditional.group[0].count, 1)
        self.assertEqual(w.then.count, 1)

    def test_failure(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "false"}
        }, then={
            "type": "count",
            "match" : {"type" : "true"}
        })
        
        ctx = Context()
        result = w.match_data(ctx, w.process_data(ctx))
        self.assertEqual(result, False)
        self.assertEqual(w.conditional.group[0].count, 1)
        self.assertEqual(w.then.count, 0)