import hashlib
import unittest

from src.cache import Cache
from src.context import Context
from src.selector import Selector, SelectorItem

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
        s: Selector = Selector.load(type="new", cache_key="test_basic")
        items = [SelectorItem(b'1'), SelectorItem(b'2'), SelectorItem(b'3'), SelectorItem(b'4')]

        result = s.run_all(self.ctx, items)
        self.assertListEqual(result, items)
        self.assertSetEqual(set(self.cache.get_file("test_basic")), set([hashlib.sha256(x.value).hexdigest().encode() for x in items]))
        
    
    def test_new(self):
        s: Selector = Selector.load(type="new", cache_key="test_new")
        items = [SelectorItem(b'1'), SelectorItem(b'2'), SelectorItem(b'3'), SelectorItem(b'4')]
        
        s.run_all(self.ctx, [items[0], items[1]])
        result = s.run_all(self.ctx, [items[1], items[2], items[3]])
        self.assertListEqual(result, [items[2], items[3]])
        self.assertSetEqual(set(self.cache.get_file("test_new")), set([hashlib.sha256(x.value).hexdigest().encode() for x in items]))
    
    def test_no_new(self):
        s: Selector = Selector.load(type="new", cache_key="test_no_new")
        items = [SelectorItem(b'1'), SelectorItem(b'2'), SelectorItem(b'3'), SelectorItem(b'4')]

        s.run_all(self.ctx, items)
        result = s.run_all(self.ctx, [items[2], items[3]])
        self.assertListEqual(result, [])
        self.assertSetEqual(set(self.cache.get_file("test_no_new")), set([hashlib.sha256(x.value).hexdigest().encode() for x in items]))
        