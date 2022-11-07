import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch


class TestLoopWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
        self.ctx.set_variable("templates", {})
    
    def tearDown(self) -> None:
        self.cache.close()
    
    def test_basic(self):
        w = Watch.load(loop={
            "static": [b'1', b'2', b'3', b'4'],
            "match" : {"type" : "true"}
        }, do={
            "type": "count",
            "match" : {"type" : "true"},
        })
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertEqual(len(w.watches), 4)
        self.assertEqual(w.watches[0].subwatch.count, 1)
        self.assertNotEqual(w.watches[0].hash, w.watches[1].hash)

    def test_all_failure(self):
        w = Watch.load(loop={
                "static": [b'1', b'2', b'3', b'4'],
                "match" : {"type" : "true"}
            }, 
            do={
                "type": "count",
                "match" : {"cond" : "1", "operator" : "eq", "comparitor" : "{{ loop }}"}
            }
        )
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, False)
        self.assertEqual(len(w.watches), 4)
        self.assertEqual(w.watches[0].subwatch.count, 1)
        self.assertEqual(w.watches[1].subwatch.count, 1)
        self.assertEqual(w.watches[2].subwatch, None)

    def test_zero_iterations(self):
        w = Watch.load(loop={
                "static": [],
                "match" : {"type" : "true"}
            }, 
            do={
                "type": "count",
                "match" : {"type" : "true"}
            }
        )
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, False)

        