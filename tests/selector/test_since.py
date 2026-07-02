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

    def test_keyed(self):
        # Dedup on a var (e.g. tag_name) rather than the value hash
        s: Selector = Selector.load(**{"type": "since", "cache_key": "tk", "key": "tag"})
        first = [SelectorItem(b'x', {"tag": b"v3"}), SelectorItem(b'x', {"tag": b"v2"}), SelectorItem(b'x', {"tag": b"v1"})]
        self.assertEqual(len(s.run_all(self.ctx, first)), 3)      # fresh cache -> all
        self.assertEqual(self.cache.get_file("tk"), b"v3")        # newest key stored

        second = [SelectorItem(b'x', {"tag": b"v4"}), SelectorItem(b'x', {"tag": b"v3"}), SelectorItem(b'x', {"tag": b"v2"})]
        result = s.run_all(self.ctx, second)
        self.assertListEqual([i.vars["tag"] for i in result], [b"v4"])
        self.assertEqual(self.cache.get_file("tk"), b"v4")

    def test_keyed_missing_key_does_not_poison(self):
        # Regression: an API error object parsed into empty-var items must not be
        # reported, and must not overwrite the cached position (which previously
        # caused the whole backlog to re-report on the next good response).
        s: Selector = Selector.load(**{"type": "since", "cache_key": "tk2", "key": "tag"})
        self.cache.put_file("tk2", b"v3.4.5")  # a real last-seen tag
        bogus = [SelectorItem(b'API rate limit exceeded'), SelectorItem(b'https://docs.github.com')]
        result = s.run_all(self.ctx, bogus)
        self.assertListEqual(result, [])                        # nothing reported
        self.assertEqual(self.cache.get_file("tk2"), b"v3.4.5")  # cache preserved

    def test_keyed_none_valued_key_is_missing(self):
        # A present-but-None key (e.g. an absent xpath field) counts as missing
        s: Selector = Selector.load(**{"type": "since", "cache_key": "tk3", "key": "tag"})
        self.cache.put_file("tk3", b"v1")
        result = s.run_all(self.ctx, [SelectorItem(b'x', {"tag": None})])
        self.assertListEqual(result, [])
        self.assertEqual(self.cache.get_file("tk3"), b"v1")
        