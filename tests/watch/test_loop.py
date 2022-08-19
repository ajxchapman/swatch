import unittest

from src.watch import Watch, Context


class TestLoopWatch(unittest.TestCase):
    def test_basic(self):
        w = Watch.load(loop={
            "data": [b'1', b'2', b'3', b'4'],
            "match" : {"type" : "true"}
        }, do={
            "type": "count",
            "match" : {"type" : "true"}
        })
        
        ctx = Context()
        result = w.process(ctx)
        self.assertEqual(result, True)
        self.assertEqual(len(w.iterations), 4)
        self.assertEqual(w.iterations[0].count, 1)
        self.assertNotEqual(w.iterations[0].hash, w.iterations[1].hash)

    def test_all_failure(self):
        w = Watch.load(loop={
                "data": [b'1', b'2', b'3', b'4'],
                "match" : {"type" : "true"}
            }, 
            operator="all", 
            do={
                "template": "{{ data }}",
                "match" : {"cond" : "1", "operator" : "eq"}
            }
        )
        
        ctx = Context()
        result = w.process(ctx)
        self.assertEqual(result, False)
        self.assertListEqual(w.matched, [True, False])
        self.assertEqual(len(w.iterations), 2)

    def test_zero_iterations(self):
        w = Watch.load(loop={
                "data": [],
                "match" : {"type" : "true"}
            }, 
            do={
                "type": "count",
                "match" : {"type" : "true"}
            }
        )
        
        ctx = Context()
        result = w.process(ctx)
        self.assertEqual(result, False)

        