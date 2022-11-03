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
        
        result = w.process(self.ctx)
        self.assertEqual(result, True)
        self.assertEqual(w.watch.count, 1)

        result = w.process(self.ctx)
        self.assertEqual(result, False)
        self.assertEqual(w.watch.count, 1)
