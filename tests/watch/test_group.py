import unittest

from src.cache import Cache
from src.context import Context
from src.loadable import _classes as LoadableClasses
from src.watch import Watch, WatchException

class TestGroupWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
    
    def tearDown(self) -> None:
        self.cache.close()

    def test_and_success(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"}
        }, {
            "type": "count",
            "match" : {"type" : "true"}
        }], operator="all")
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertEqual(w.watches[0].count, 1)
        self.assertEqual(w.watches[1].count, 1)

    def test_and_failure(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "false"}
        }, {
            "type": "count",
            "match" : {"type" : "true"}
        }], operator="all")
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, False)
        self.assertEqual(w.watches[0].count, 1)
        self.assertEqual(len(w.watches), 1) # Ensure early exit

    def test_or_success(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"}
        }, {
            "type": "count",
            "match" : {"type" : "false"}
        }], operator="any")
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertEqual(w.watches[0].count, 1)
        self.assertEqual(w.watches[1].count, 1)

    def test_or_failure(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "false"}
        }, {
            "type": "count",
            "match" : {"type" : "false"}
        }], operator="any")
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, False)
        self.assertEqual(w.watches[0].count, 1)
        self.assertEqual(w.watches[1].count, 1)

    def test_last_success(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "false"}
        }, {
            "type": "count",
            "match" : {"type" : "true"}
        }], operator="last")
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertEqual(w.watches[0].count, 1)
        self.assertEqual(w.watches[1].count, 1)


    def test_last_failure(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"}
        }, {
            "type": "count",
            "match" : {"type" : "false"}
        }], operator="last")
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, False)
        self.assertEqual(w.watches[0].count, 1)
        self.assertEqual(w.watches[1].count, 1)

    def test_before(self):
        w = Watch.load(group=[{
            "type": "static",
            "match" : {"type" : "true"}
        }], before={"type": "count"})

        initialCount = LoadableClasses['watch_count'].class_count
        w.process(self.ctx)
        self.assertEqual(LoadableClasses['watch_count'].class_count, initialCount + 1)

    def test_before_list(self):
        w = Watch.load(group=[{
            "type": "static",
            "match" : {"type" : "true"}
        }], before=[{"type": "count"}, {"type": "count"}])

        initialCount = LoadableClasses['watch_count'].class_count
        w.process(self.ctx)
        self.assertEqual(LoadableClasses['watch_count'].class_count, initialCount + 2)
    
    def test_before_exception(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"}
        }], before={"type": "throw"})

        with self.assertRaises(WatchException):
            w.process(self.ctx)
        self.assertEqual(len(w.watches), 0)

    def test_after(self):
        w = Watch.load(group=[{
            "type": "static",
            "match" : {"type" : "true"}
        }], after={"type": "count"})

        initialCount = LoadableClasses['watch_count'].class_count
        w.process(self.ctx)
        self.assertEqual(LoadableClasses['watch_count'].class_count, initialCount + 1)