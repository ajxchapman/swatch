import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch


class TestRangeWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)

    def tearDown(self) -> None:
        self.cache.close()

    def test_default_key(self):
        # The default key maps a bare `range: N` to the `to` bound
        w = Watch.load(range=3, match={"type": "true"})
        w.process(self.ctx)
        self.assertListEqual([x.value for x in self.ctx["data"]], [b'0', b'1', b'2'])

    def test_from_to_step(self):
        w = Watch.load(type="range", match={"type": "true"}, **{"from": 1, "to": 10, "step": 3})
        w.process(self.ctx)
        self.assertListEqual([x.value for x in self.ctx["data"]], [b'1', b'4', b'7'])
