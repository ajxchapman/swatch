import unittest

from src.match import Match
from src.context import Context
from src.cache import Cache

class TestCacheMatch(unittest.TestCase):
    def test_1(self):
        m: Match = Match.load(type="cache")

        ctx = Context()
        ctx.set_variable("cache", Cache())
        ctx.set_variable("hash", "test")
        
        self.assertEqual(m.match(ctx, [b'data']), True)
        self.assertEqual(m.match(ctx, [b'data']), False)
