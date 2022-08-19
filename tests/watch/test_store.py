import unittest

from src.cache import Cache
from src.context import Context
from src.watch import Watch

class TestStoreWatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.cache = Cache()
        self.ctx.set_variable("cache", self.cache)
    
    def tearDown(self) -> None:
        self.cache.close()
    
    def test_store(self):
        w = Watch.load(cmd="echo 123", store="VALUE", selectors=[{"type": "strip"}], match="None")
        
        w.process(self.ctx)
        self.assertListEqual(self.ctx.get_variable("VALUE"), [b'123'])