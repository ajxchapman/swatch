import unittest

from src.context import Context
from src.selector import Selector, SelectorItem

RSS = (
    b"<rss><channel>"
    b"<item><title><![CDATA[Hello]]></title><description>World</description><link>http://x/1</link></item>"
    b"<item><title>Foo</title><description>Bar</description><link>http://x/2</link></item>"
    b"</channel></rss>"
)

ATOM = (
    b'<feed xmlns="http://www.w3.org/2005/Atom">'
    b'<entry><title>Post</title>'
    b'<link rel="self" href="http://x/self"/>'
    b'<link rel="alternate" type="text/html" href="http://x/post"/>'
    b'</entry></feed>'
)


class TestXPathSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()

    def test_extract_vars(self):
        s = Selector.load(**{
            "type": "xpath",
            "select": "//item",
            "vars": {"title": "title/text()", "summary": "description/text()", "link": "link/text()"},
        })
        res = s.execute(self.ctx, [SelectorItem(RSS)])
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].vars["title"], b"Hello")   # CDATA unwrapped
        self.assertEqual(res[0].vars["summary"], b"World")
        self.assertEqual(res[0].vars["link"], b"http://x/1")
        self.assertEqual(res[1].vars["title"], b"Foo")
        self.assertEqual(res[1].vars["link"], b"http://x/2")

    def test_default_key_is_select(self):
        # `- xpath: '//item/title/text()'` maps the bare value to `select`
        s = Selector.load(xpath="//item/title/text()")
        res = s.execute(self.ctx, [SelectorItem(RSS)])
        self.assertListEqual([x.value for x in res], [b"Hello", b"Foo"])

    def test_atom_default_namespace_and_attribute(self):
        # Default namespace is stripped; attribute extraction via @href works
        s = Selector.load(**{
            "type": "xpath",
            "select": "//entry",
            "vars": {
                "title": "title/text()",
                "link": 'link[@rel="alternate"][@type="text/html"]/@href',
            },
        })
        res = s.execute(self.ctx, [SelectorItem(ATOM)])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].vars["title"], b"Post")
        self.assertEqual(res[0].vars["link"], b"http://x/post")

    def test_missing_field_is_none(self):
        s = Selector.load(**{
            "type": "xpath",
            "select": "//item",
            "vars": {"title": "title/text()", "author": "creator/text()"},
        })
        res = s.execute(self.ctx, [SelectorItem(RSS)])
        self.assertEqual(res[0].vars["title"], b"Hello")
        self.assertIsNone(res[0].vars["author"])

    def test_vars_carry_forward(self):
        # Existing vars on the input item are preserved on the extracted items
        item = SelectorItem(RSS, vars={"source": b"calif"})
        s = Selector.load(**{"type": "xpath", "select": "//item", "vars": {"link": "link/text()"}})
        res = s.execute(self.ctx, [item])
        self.assertEqual(res[0].vars["source"], b"calif")
        self.assertEqual(res[0].vars["link"], b"http://x/1")

    def test_malformed_xml_recovers(self):
        # recover=True should salvage a truncated document rather than raising
        s = Selector.load(**{"type": "xpath", "select": "//item", "vars": {"title": "title/text()"}})
        res = s.execute(self.ctx, [SelectorItem(b"<rss><channel><item><title>Only</title></item>")])
        self.assertEqual(res[0].vars["title"], b"Only")
