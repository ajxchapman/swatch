import unittest

from src.watch import Watch, Context

class TestGroupWatch(unittest.TestCase):
    def test_and_success(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"}
        }, {
            "type": "count",
            "match" : {"type" : "true"}
        }], operator="all")
        
        ctx = Context()
        result = w.process(ctx)
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
        
        ctx = Context()
        result = w.process(ctx)
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
        
        ctx = Context()
        result = w.process(ctx)
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
        
        ctx = Context()
        result = w.process(ctx)
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
        
        ctx = Context()
        result = w.process(ctx)
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
        
        ctx = Context()
        result = w.process(ctx)
        self.assertEqual(result, False)
        self.assertEqual(w.group[0].count, 1)
        self.assertEqual(w.group[1].count, 1)
