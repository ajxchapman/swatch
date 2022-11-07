import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch, render_comment


class TestCommentWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
    
    def tearDown(self) -> None:
        self.cache.close()

    def test_basic(self):
        w = Watch.load(**{
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment"
        })

        w.process(self.ctx)
        self.assertListEqual(w.get_comment(self.ctx), ["Comment"])
        self.assertEqual(render_comment(w.get_comment(self.ctx)), "Comment")

    def test_group_comment(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment1.1"
        }, {
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment1.2"
        }], comment="Comment1")

        _, comment, _ = w.process(self.ctx)

        self.assertListEqual(comment, ["Comment1", ["Comment1.1", "Comment1.2"]])
        self.assertEqual(render_comment(comment), "Comment1\n  Comment1.1\n  Comment1.2")
    
    def test_group_comment_blank(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment1.1"
        }, {
            "type": "count",
            "match" : {"type" : "true"}
        }, {
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment1.2"
        }], comment="Comment1")

        _, comment, _ = w.process(self.ctx)

        self.assertListEqual(comment, ["Comment1", ["Comment1.1", "Comment1.2"]])
        self.assertEqual(render_comment(comment), "Comment1\n  Comment1.1\n  Comment1.2")

    def test_group_fail_comment(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment Success"
        }, {
            "type": "count",
            "match" : {"type" : "false"},
            "comment" : "Comment Failure"
        }])

        _, comment, _ = w.process(self.ctx)

        self.assertListEqual(comment, ["Comment Success"])
        self.assertEqual(render_comment(comment), "Comment Success")

    def test_group_nocomment(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment1"
        }, {
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment2"
        }])

        _, comment, _ = w.process(self.ctx)

        self.assertListEqual(comment, ["Comment1", "Comment2"])
        self.assertEqual(render_comment(comment), "Comment1\nComment2")
    
    def test_group_nocomment_blank(self):
        w = Watch.load(group=[{
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment1"
        }, {
            "type": "count",
            "match" : {"type" : "true"}
        }, {
            "type": "count",
            "match": {"type" : "true"},
            "comment": "Comment2"
        }])

        _, comment, _ = w.process(self.ctx)

        self.assertListEqual(comment, ["Comment1", "Comment2"])
        self.assertEqual(render_comment(comment), "Comment1\nComment2")

    def test_group_nested(self):
        w = Watch.load(group=[{
            "group": [{
                "group": [{
                    "type": "count",
                    "match" : {"type" : "true"},
                    "comment" : "Comment1.1.1"
                }]
            }],
            "comment": "Comment1.1"
        }, {
            "group": [{
                "type": "count",
                "match": {"type" : "true"},
            }],
            "comment": "Comment1.2"
        }], comment="Comment1")

        _, comment, _ = w.process(self.ctx)
        self.assertEqual(render_comment(comment), "Comment1\n  Comment1.1\n    Comment1.1.1\n  Comment1.2")

    def test_conditional_comment(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "true"}
        }, then={
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment1.1"
        }, comment="Comment1")

        _, comment, _ = w.process(self.ctx)

        self.assertListEqual(comment, ["Comment1", ["Comment1.1"]])
        self.assertEqual(render_comment(comment), "Comment1\n  Comment1.1")

    def test_conditional_nocomment(self):
        w = Watch.load(conditional={
            "type": "count",
            "match" : {"type" : "true"}
        }, then={
            "type": "count",
            "match" : {"type" : "true"},
            "comment" : "Comment"
        })

        _, comment, _ = w.process(self.ctx)

        self.assertListEqual(comment, ["Comment"])
        self.assertEqual(render_comment(comment), "Comment")