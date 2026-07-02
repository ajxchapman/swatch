import hashlib
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
        with open(os.path.join(self.cache.cache_dir, hashlib.sha256("filekey".encode()).hexdigest()), "rb") as f:
            data = f.read()

        self.assertEqual(self.cache.get_file("filekey"), b'data')
        self.assertNotEqual(data, b'data')

    def test_get_entry_default(self):
        self.assertIsNone(self.cache.get_entry("doesnotexist"))
        self.assertEqual(self.cache.get_entry("doesnotexist", 0), 0)


class TestCacheClose(unittest.TestCase):
    def test_close_bare_filename(self):
        # Regression: closing a cache whose path has no directory component
        # previously called os.makedirs("") and raised FileNotFoundError.
        rndname = "".join(random.choices("0123456789abcdef", k=12)) + ".tar.gz"
        cwd = os.getcwd()
        os.chdir("/tmp")
        try:
            cache = Cache(cache_path=rndname)
            cache.put_entry("k", "v")
            cache.close()
            self.assertTrue(os.path.isfile(os.path.join("/tmp", rndname)))
        finally:
            if os.path.isfile(os.path.join("/tmp", rndname)):
                os.unlink(os.path.join("/tmp", rndname))
            os.chdir(cwd)
