import unittest

from src.context import Context
from src.selector import Selector, SelectorItem


class TestJoinSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_join(self):
        s: Selector = Selector.load(type="join", sep="-")
        data = [SelectorItem(b'1'), SelectorItem(b'2'), SelectorItem(b'3')]

        result = s.execute(self.ctx, data)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].value, b'1-2-3')

    def test_join_empty(self):
        s: Selector = Selector.load(type="join", sep="-")
        result = s.execute(self.ctx, [])
        self.assertListEqual(result, [])


class TestPickSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_pick(self):
        s: Selector = Selector.load(type="pick", index=[0, 2])
        data = [SelectorItem(b'a'), SelectorItem(b'b'), SelectorItem(b'c'), SelectorItem(b'd')]

        result = s.execute(self.ctx, data)
        self.assertListEqual([x.value for x in result], [b'a', b'c'])

    def test_pick_scalar(self):
        # A single index should be coerced to a list
        s: Selector = Selector.load(type="pick", index=1)
        data = [SelectorItem(b'a'), SelectorItem(b'b'), SelectorItem(b'c')]

        result = s.execute(self.ctx, data)
        self.assertListEqual([x.value for x in result], [b'b'])

    def test_pick_empty(self):
        s: Selector = Selector.load(type="pick", index=[0])
        result = s.execute(self.ctx, [])
        self.assertListEqual(result, [])


class TestSliceSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_slice(self):
        s: Selector = Selector.load(type="slice", start=1, end=3)
        data = [SelectorItem(b'a'), SelectorItem(b'b'), SelectorItem(b'c'), SelectorItem(b'd')]

        result = s.execute(self.ctx, data)
        self.assertListEqual([x.value for x in result], [b'b', b'c'])


class TestBytesSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_bytes(self):
        s: Selector = Selector.load(type="bytes", start=1, end=3)
        result = s.run(self.ctx, SelectorItem(b'abcdef'))
        self.assertEqual(result[0].value, b'bc')


class TestStripTagsSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_striptags(self):
        s: Selector = Selector.load(type="striptags")
        result = s.run(self.ctx, SelectorItem(b'<p>Hello <b>World</b></p>'))
        self.assertEqual(result[0].value, b'Hello World')

    def test_striptags_replacement(self):
        s: Selector = Selector.load(type="striptags", replacement=" ")
        result = s.run(self.ctx, SelectorItem(b'a<br/>b'))
        self.assertEqual(result[0].value, b'a b')


class TestFormatSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_format(self):
        s: Selector = Selector.load(type="format", format="{{ vars.name }}=hello")
        item = SelectorItem(b'x', vars={"name": b"greeting"})

        result = s.run(self.ctx, item)
        self.assertEqual(result[0].value, b'greeting=hello')

    def test_format_var(self):
        s: Selector = Selector.load(type="format", format="{{ vars.name }}", var="out")
        item = SelectorItem(b'x', vars={"name": b"greeting"})

        result = s.run(self.ctx, item)
        self.assertEqual(result[0].vars["out"], b'greeting')


class TestRegexSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_named_groups(self):
        s: Selector = Selector.load(type="regex", regex=r"(?P<key>[a-z]+)=(?P<value>[0-9]+)")
        result = s.run(self.ctx, SelectorItem(b'abc=123'))
        self.assertEqual(result[0].vars["key"], b'abc')
        self.assertEqual(result[0].vars["value"], b'123')

    def test_all(self):
        s: Selector = Selector.load(type="regex", regex=r"[0-9]+", all=True)
        result = s.run(self.ctx, SelectorItem(b'1 a 2 b 3'))
        self.assertListEqual([x.value for x in result], [b'1', b'2', b'3'])

    def test_single(self):
        s: Selector = Selector.load(type="regex", regex=r"[0-9]+")
        result = s.run(self.ctx, SelectorItem(b'1 a 2 b 3'))
        self.assertListEqual([x.value for x in result], [b'1'])
