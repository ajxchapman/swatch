import hashlib
import unittest

from src.cache import Cache
from src.context import Context
from src.selector import Selector

class TestSinceSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)

    def tearDown(self) -> None:
        self.cache.close()

    def test_empty(self):
        s: Selector = Selector.load(type="since", key="test_empty")
        data = [b'1', b'2', b'3', b'4']

        result = s.run_all(self.ctx, data)
        self.assertListEqual(result, data)
        self.assertTrue(self.cache.has_entry("test_empty"))
        self.assertEqual(self.cache.get_entry("test_empty"), hashlib.sha256(b'1').hexdigest())
    
    def test_new(self):
        s: Selector = Selector.load(type="since", key="test_new")
        
        s.run_all(self.ctx, [b'3', b'4'])
        result = s.run_all(self.ctx, [b'1', b'2', b'3', b'4'])
        self.assertListEqual(result, [b'1', b'2'])
        self.assertTrue(self.cache.has_entry("test_new"))
        self.assertEqual(self.cache.get_entry("test_new"), hashlib.sha256(b'1').hexdigest())
    
    def test_no_new(self):
        s: Selector = Selector.load(type="since", key="test_no_new")

        s.run_all(self.ctx, [b'1', b'2', b'3', b'4'])
        result = s.run_all(self.ctx, [b'1', b'2', b'3', b'4'])
        self.assertListEqual(result, [])
        self.assertTrue(self.cache.has_entry("test_no_new"))
        self.assertEqual(self.cache.get_entry("test_no_new"), hashlib.sha256(b'1').hexdigest())
        