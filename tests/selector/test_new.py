import unittest

from src.cache import Cache
from src.context import Context
from src.selector import Selector

class TestNewSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.hash = "testnew"
        self.ctx.set_variable("cache", self.cache)
        self.ctx.set_variable("hash", self.hash)

    def tearDown(self) -> None:
        self.cache.close()

    def test_basic(self):
        s: Selector = Selector.load(type="new", key="test_basic")
        data = [b'1', b'2', b'3', b'4']

        result = s.run_all(self.ctx, data)
        self.assertListEqual(result, data)
        self.assertSetEqual(set(self.cache.get_file("test_basic")), set([b'1', b'2', b'3', b'4']))
    
    def test_new(self):
        s: Selector = Selector.load(type="new", key="test_new")
        
        s.run_all(self.ctx, [b'1', b'2'])
        result = s.run_all(self.ctx, [b'2', b'3', b'4'])
        self.assertListEqual(result, [b'3', b'4'])
        self.assertSetEqual(set(self.cache.get_file("test_new")), set([b'1', b'2', b'3', b'4']))
    
    def test_no_new(self):
        s: Selector = Selector.load(type="new", key="test_no_new")

        s.run_all(self.ctx, [b'1', b'2', b'3', b'4'])
        result = s.run_all(self.ctx, [b'2', b'3'])
        self.assertListEqual(result, [])
        self.assertSetEqual(set(self.cache.get_file("test_no_new")), set([b'1', b'2', b'3', b'4']))
        