import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch


class TestLoopWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
    
    def tearDown(self) -> None:
        self.cache.close()
    
    def test_basic(self):
        w = Watch.load(loop={
            "data": [b'1', b'2', b'3', b'4'],
            "match" : {"type" : "true"}
        }, do={
            "type": "count",
            "match" : {"type" : "true"}
        })
        
        result = w.process(self.ctx)
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
                "data": ["{{ data }}"],
                "match" : {"cond" : "1", "operator" : "eq"}
            }
        )
        
        result = w.process(self.ctx)
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
        
        result = w.process(self.ctx)
        self.assertEqual(result, False)

        