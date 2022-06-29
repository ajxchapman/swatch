import os
import random
import unittest

from src.cache import Cache

class TestCache(unittest.TestCase):
    def setUp(self) -> None:
        rndname = "".join(random.choices("0123456789abcdef", k=12))
        self.cache = Cache(f"/tmp/{rndname}.tar.gz")
        self.cache.put_entry("entrykey", "data")
        self.cache.put_file("filekey", b'data')
    
    def tearDown(self) -> None:
        if not self.cache.closed:
            self.cache.close()
        if os.path.isfile(self.cache.cache_path):
            os.unlink(self.cache.cache_path)

    def test_1(self):
        self.assertEqual(self.cache.get_entry("entrykey"), "data")
        self.assertIsNone(self.cache.get_entry("doesnotexist"))
        self.assertEqual(self.cache.get_file("filekey"), b'data')