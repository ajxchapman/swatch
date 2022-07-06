import os
import random
import unittest

from cryptography.fernet import Fernet

from src.cache import Cache

class TestCache(unittest.TestCase):
    def setUp(self) -> None:
        rndname = "".join(random.choices("0123456789abcdef", k=12))
        self.cache = Cache(cache_path=f"/tmp/{rndname}.tar.gz", encryption_key=Fernet.generate_key())
        self.cache.put_entry("entrykey", "data")
        self.cache.put_file("filekey", b'data')
    
    def tearDown(self) -> None:
        if not self.cache.closed:
            self.cache.close()
        if os.path.isfile(self.cache.cache_path):
            os.unlink(self.cache.cache_path)

    def test_basic(self):
        self.assertEqual(self.cache.get_entry("entrykey"), "data")
        self.assertIsNone(self.cache.get_entry("doesnotexist"))
        self.assertEqual(self.cache.get_file("filekey"), b'data')

    def test_file_encryption(self):
        with open(os.path.join(self.cache.cache_dir, "filekey"), "rb") as f:
            data = f.read()
        
        self.assertEqual(self.cache.get_file("filekey"), b'data')
        self.assertNotEqual(data, b'data')
