import hashlib
import unittest

from src.cache import Cache
from src.context import Context
from src.selector import Selector, SelectorItem

class TestSinceSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)

    def tearDown(self) -> None:
        self.cache.close()

    def test_empty(self):
        s: Selector = Selector.load(type="since", cache_key="test_empty")
        items = [SelectorItem(b'1'), SelectorItem(b'2'), SelectorItem(b'3'), SelectorItem(b'4')]

        result = s.run_all(self.ctx, items)
        self.assertListEqual(result, items)
        self.assertEqual(self.cache.get_file("test_empty"), hashlib.sha256(b'1').hexdigest().encode())
    
    def test_new(self):
        s: Selector = Selector.load(type="since", cache_key="test_new")
        items = [SelectorItem(b'1'), SelectorItem(b'2'), SelectorItem(b'3'), SelectorItem(b'4')]
        
        s.run_all(self.ctx, [items[2], items[3]])
        result = s.run_all(self.ctx, items)
        self.assertListEqual(result, [items[0], items[1]])
        self.assertEqual(self.cache.get_file("test_new"), hashlib.sha256(b'1').hexdigest().encode())
    
    def test_no_new(self):
        s: Selector = Selector.load(type="since", cache_key="test_no_new")
        items = [SelectorItem(b'1'), SelectorItem(b'2'), SelectorItem(b'3'), SelectorItem(b'4')]

        s.run_all(self.ctx, items)
        result = s.run_all(self.ctx, items)
        self.assertListEqual(result, [])
        self.assertEqual(self.cache.get_file("test_no_new"), hashlib.sha256(b'1').hexdigest().encode())
        