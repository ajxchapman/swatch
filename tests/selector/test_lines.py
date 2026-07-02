import unittest

from src.context import Context
from src.selector import Selector, SelectorItem

class TestLinesSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_basic(self):
        s: Selector = Selector.load(type="lines")
        item = SelectorItem(b'a\nb\nc')

        result = s.run(self.ctx, item)
        self.assertListEqual([x.value for x in result], [b'a', b'b', b'c'])

    def test_keepends(self):
        s: Selector = Selector.load(type="lines", keepends=True)
        item = SelectorItem(b'a\nb\nc')

        result = s.run(self.ctx, item)
        self.assertListEqual([x.value for x in result], [b'a\n', b'b\n', b'c'])

    def test_html_disabled(self):
        # With html disabled (the default) <br/> should not introduce line breaks.
        # Regression: previously the `html` module was checked instead of `self.html`,
        # so this option was always treated as enabled.
        s: Selector = Selector.load(type="lines", html=False)
        item = SelectorItem(b'a<br/>b<br/>c')

        result = s.run(self.ctx, item)
        self.assertListEqual([x.value for x in result], [b'a<br/>b<br/>c'])

    def test_html_enabled(self):
        s: Selector = Selector.load(type="lines", html=True)
        item = SelectorItem(b'a<br/>b</p>c')

        result = s.run(self.ctx, item)
        self.assertListEqual([x.value for x in result], [b'a<br/>', b'b</p>', b'c'])
