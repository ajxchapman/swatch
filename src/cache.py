import os
import re
import shutil
import subprocess
import tempfile
import yaml

KEY_EXPR = r"^[A-Za-z0-9_-]+$"

class CacheException(Exception):
    pass

class Cache:
    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self.cache_dir = tempfile.mkdtemp()
        self.cache = {}
        self.closed = False

        if os.path.isfile(self.cache_path):
            p = subprocess.run(["tar", "-C", self.cache_dir, "-xzf", self.cache_path])
            if p.returncode != 0:
                shutil.rmtree(self.cache_dir)
                raise CacheException("Error extracting cache")

            if os.path.isfile(os.path.join(self.cache_dir, "cache.yaml")):
                with open(os.path.join(self.cache_dir, "cache.yaml")) as f:
                    cache = yaml.safe_load(f)

        if not isinstance(self.cache, dict):
            self.cache = {}

    def close(self) -> None:
        self.closed = True
        with open(os.path.join(self.cache_dir, "cache.yaml"), "w") as f:
            yaml.dump(self.cache, f, default_flow_style=False)
        
        if not os.path.isdir(os.path.dirname(self.cache_path)):
            os.makedirs(os.path.dirname(self.cache_path))
        p = subprocess.run(["tar", "-C", self.cache_dir, "-czf", self.cache_path, "."])
        
        shutil.rmtree(self.cache_dir)
        if p.returncode != 0:
            raise CacheException("Error compressing cache")


    def get_file(self, key: str) -> bytes:
        if not re.match(KEY_EXPR, key):
            raise CacheException(f"Invalid cache key: '{key}'")

        if os.path.isfile(os.path.join(self.cache_dir, key)):
            with open(os.path.join(self.cache_dir, key), "rb") as f:
                return f.read()

    def put_file(self, key: str, data: bytes) -> None:
        if not re.match(KEY_EXPR, key):
            raise CacheException(f"Invalid cache key: '{key}'")
        
        with open(os.path.join(self.cache_dir, key), "wb") as f:
            return f.write(data)

    def get_entry(self, key: str) -> str:
        if not re.match(KEY_EXPR, key):
            raise CacheException(f"Invalid cache key: '{key}'")
        
        return self.cache.get(key)
    
    def put_entry(self, key: str, data: str) -> None:
        if not re.match(KEY_EXPR, key):
            raise CacheException(f"Invalid cache key: '{key}'")

        self.cache[key] = data