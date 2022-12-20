import unittest

from src.cache import Cache
from src.context import Context
from src.loadable import Loadable
from src.watch import Watch, WatchException


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

    def test_before_list(self):
        w = Watch.load(type="static",
            match={"type" : "true"},
            before=[{"type": "count"}, {"type": "count"}]
        )

        initialCount = Loadable._Loadable__classes['watch_count'].class_count
        w.process(self.ctx)
        self.assertEqual(Loadable._Loadable__classes['watch_count'].class_count, initialCount + 2)
    
    def test_before_exception(self):
        w = Watch.load(type="count",
            match={"type" : "true"},
            before={"type": "throw"}
        )

        with self.assertRaises(WatchException):
            w.process(self.ctx)
        self.assertEqual(w.count, 0)

    def test_after(self):
        w = Watch.load(type="static",
            match={"type" : "true"},
            after={"type": "count"}
        )

        initialCount = Loadable._Loadable__classes['watch_count'].class_count
        w.process(self.ctx)
        self.assertEqual(Loadable._Loadable__classes['watch_count'].class_count, initialCount + 1)