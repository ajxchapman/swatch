import unittest

from src.cache import Cache
from src.context import Context
from src.loadable import Loadable
from src.watch import Watch, WatchException

templates = {
    "count" : {
        "type" : "count",
        "match" : {"type" : "true"}
    },
    "static" : {
        "static": ["result {{ k1 }}"],
        "match" : {"type" : "true"}
    },
    "render0" : {},
    "render1" : {
        "body" : None
    },
    "render_key" : {
        "key" : {"body" : None}
    },
    "render_dict" : {
        "key" : {"body" : {"k1" : "v1"}}
    },
    "render_list" : {
        "key" : {"body" : ["v1", "v2"]}
    },
    "render_static_class" : {
        "static" : [1]
    }
}


class TestTemplateWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
        self.ctx.set_variable("templates", templates)
    
    def tearDown(self) -> None:
        self.cache.close()

    def test_count(self):
        w = Watch.load(template="count")
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertEqual(w.subwatch.count, 1)

    def test_data(self):
        w = Watch.load(template="static", variables={"k1" : "v1"})
        
        trigger, _, _ = w.process(self.ctx)
        self.assertEqual(trigger, True)
        self.assertLessEqual(self.ctx.get_variable(w.subwatch.hash), ["result v1"])

    def test_hash(self):
        w1 = Watch.load(template="static", variables={"k1" : "v1"})
        w2 = Watch.load(template="static", variables={"k1" : "v2"})
        
        w1.process(self.ctx)
        w2.process(self.ctx)

        self.assertNotEqual(w1.hash, w2.hash)
        self.assertNotEqual(w1.subwatch.hash, w2.subwatch.hash)

    def test_render(self):
        w = Watch.load(template="render0", body={"test" : 1})
        self.assertDictEqual(w.render_template(self.ctx), {"test" : 1})

    def test_render1(self):
        w = Watch.load(template="render1", body={"test" : 1})
        self.assertDictEqual(w.render_template(self.ctx), {"test" : 1})

    def test_render_body(self):
        w = Watch.load(template="render_key", body={"test" : 1})
        self.assertDictEqual(w.render_template(self.ctx), {"key" : {"test" : 1}})

    def test_render_kwargs(self):
        w = Watch.load(template="render_key", test=1)
        self.assertDictEqual(w.render_template(self.ctx), {"key" : {"test" : 1}})

    def test_render_dict(self):
        w = Watch.load(template="render_dict", body={"test" : 1})
        self.assertDictEqual(w.render_template(self.ctx), {"key" : {"k1" : "v1", "test" : 1}})

    def test_render_dict_list_error(self):
        w = Watch.load(template="render_dict", body=[1, 2])
        with self.assertRaises(WatchException):
            w.render_template(self.ctx)

    def test_render_list(self):
        w = Watch.load(template="render_list", body=[1, 2])
        self.assertDictEqual(w.render_template(self.ctx), {"key" : ["v1", "v2", 1, 2]})

    def test_render_list_dict_error(self):
        w = Watch.load(template="render_list", body={"test" : 1})
        with self.assertRaises(WatchException):
            w.render_template(self.ctx)

    def test_loadable_class_template_precedence(self):
        w = Watch.load(template="render_static_class", body={"count" : None})
        w = Watch.load(**w.render_template(self.ctx))
        self.assertIsInstance(w, Loadable._Loadable__classes['watch_static'])
    
    def test_loadable_class_body__precedence(self):
        w = Watch.load(template="render0", body={"count" : None})
        w = Watch.load(**w.render_template(self.ctx))
        self.assertIsInstance(w, Loadable._Loadable__classes['watch_count'])