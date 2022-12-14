import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch


class TestOnceWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
    
    def tearDown(self) -> None:
        self.cache.close()

    def test_once(self):
        w = Watch.load(once={
            "type": "count",
            "match" : {"type" : "true"}
        })
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertEqual(w.watches[0].count, 1)

        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, False)
        self.assertEqual(w.watches[0].count, 1)
