import unittest

from src.cache import Cache
from src.context import Context
from src.selector import Selector, SelectorItem


class TestDictSelectors(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)

    def tearDown(self) -> None:
        self.cache.close()

    def test_store_and_load(self):
        store: Selector = Selector.load(type="dictstore", cache_key="d", key="k")
        items = [
            SelectorItem(b'one', vars={"k": b"1", "extra": b"a"}),
            SelectorItem(b'two', vars={"k": b"2", "extra": b"b"}),
        ]
        result = store.run_all(self.ctx, items)
        # dictstore passes items through unchanged
        self.assertListEqual(result, items)

        # A later load enriches matching items with the stored vars
        load: Selector = Selector.load(type="dictload", cache_key="d", key="k")
        lookup = [SelectorItem(b'', vars={"k": b"1"})]
        loaded = load.run_all(self.ctx, lookup)
        self.assertEqual(loaded[0].vars["extra"], b'a')

    def test_load_filter(self):
        store: Selector = Selector.load(type="dictstore", cache_key="d2", key="k")
        store.run_all(self.ctx, [SelectorItem(b'one', vars={"k": b"1", "extra": b"a"})])

        load: Selector = Selector.load(type="dictload", cache_key="d2", key="k", filter=True)
        lookup = [
            SelectorItem(b'', vars={"k": b"1"}),
            SelectorItem(b'', vars={"k": b"missing"}),
        ]
        loaded = load.run_all(self.ctx, lookup)
        # Only the item present in the store survives the filter
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].vars["extra"], b'a')


class TestJqSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_scalar(self):
        s: Selector = Selector.load(type="jq", value=".[].name")
        item = SelectorItem(b'[{"name": "a"}, {"name": "b"}]')
        result = s.run(self.ctx, item)
        self.assertListEqual([x.value for x in result], [b'a', b'b'])

    def test_object_to_vars(self):
        s: Selector = Selector.load(type="jq", value=".[]")
        item = SelectorItem(b'[{"name": "a", "id": 1}]')
        result = s.run(self.ctx, item)
        self.assertEqual(result[0].vars["name"], b'a')
        self.assertEqual(result[0].vars["id"], b'1')

    def test_scalar_int(self):
        # Regression: a jq expression yielding a non-string scalar raised
        # AttributeError because the else branch assumed a dict.
        s: Selector = Selector.load(type="jq", value=".[].id")
        item = SelectorItem(b'[{"id": 5}, {"id": 6}]')
        result = s.run(self.ctx, item)
        self.assertListEqual([x.value for x in result], [b'5', b'6'])
