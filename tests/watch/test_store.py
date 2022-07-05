import unittest

from src.watch import Watch, Context

class TestStoreWatch(unittest.TestCase):
    def test_store(self):
        w = Watch.load(cmd="echo 123", store="VALUE", selectors=[{"type": "strip"}])
        
        ctx = Context()
        w.process_data(ctx)
        self.assertEqual(ctx.get_variable("VALUE"), "123")