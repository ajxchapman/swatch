import unittest

from src.watch import Watch, Context

class TestStoreWatch(unittest.TestCase):
    def test_store(self):
        w = Watch.load(cmd="echo 123", store="VALUE", selectors=[{"type": "strip"}])
        
        ctx = Context()
        w.process_data(ctx)
        self.assertListEqual(ctx.get_variable("VALUE"), [b'123'])