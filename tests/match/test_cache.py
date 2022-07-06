import unittest

from src.match import Match
from src.context import Context
from src.cache import Cache

class TestCacheMatch(unittest.TestCase):
    def test_1(self):
        m: Match = Match.load(type="cache")

        ctx = Context()
        ctx.set_variable("cache", Cache(cache_path="test"))
        ctx.set_variable("key", "test")
        
        self.assertEqual(m.match(ctx, [b'data']), True)
        self.assertEqual(m.match(ctx, [b'data']), False)
