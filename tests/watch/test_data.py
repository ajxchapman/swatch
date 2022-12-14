import unittest

from src.cache import Cache
from src.context import Context
from src.loadable import Loadable
from src.watch import Watch


class TestDataWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)

    def test_before(self):
        w = Watch.load(type="static",
            match={"type" : "true"},
            before={"type": "count"}
        )

        initialCount = Loadable._Loadable__classes['watch_count'].class_count
        w.process(self.ctx)
        self.assertEqual(Loadable._Loadable__classes['watch_count'].class_count, initialCount + 1)

    def test_after(self):
        w = Watch.load(type="static",
            match={"type" : "true"},
            after={"type": "count"}
        )

        initialCount = Loadable._Loadable__classes['watch_count'].class_count
        w.process(self.ctx)
        self.assertEqual(Loadable._Loadable__classes['watch_count'].class_count, initialCount + 1)