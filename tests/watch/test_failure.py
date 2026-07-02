import logging
import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch


class TestFailureHandling(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
        self.ctx.set_variable("config", {})
        self.ctx.set_variable("watch_file", "test.yml")
        # Suppress the expected error logging emitted on a failing watch
        self._watch_logger = logging.getLogger("src.watch")
        self._prev_level = self._watch_logger.level
        self._watch_logger.setLevel(logging.CRITICAL)

    def tearDown(self) -> None:
        self._watch_logger.setLevel(self._prev_level)
        self.cache.close()

    def test_first_failure_increments_count(self):
        # Regression: on the very first failure the cached failure count did not
        # exist, and `None + 1` raised a TypeError that escaped execute().
        w = Watch.load(type="throw")
        w.execute(self.ctx)
        self.assertEqual(self.cache.get_entry(f"{w.hash}-failures"), 1)

    def test_repeated_failures_accumulate(self):
        w = Watch.load(type="throw")
        w.execute(self.ctx)
        w.execute(self.ctx)
        w.execute(self.ctx)
        self.assertEqual(self.cache.get_entry(f"{w.hash}-failures"), 3)

    def test_success_resets_failure_count(self):
        w = Watch.load(type="throw")
        w.execute(self.ctx)
        self.assertEqual(self.cache.get_entry(f"{w.hash}-failures"), 1)

        # A successful watch on the same hash space clears the count
        ok = Watch.load(type="true", match={"type": "true"})
        # Force the same hash so the failure/success share a counter key
        ok.hash = w.hash
        ok.execute(self.ctx)
        self.assertEqual(self.cache.get_entry(f"{w.hash}-failures"), 0)
