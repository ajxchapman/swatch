import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import typing
import yaml

from cryptography.fernet import Fernet

KEY_EXPR = r"^[A-Za-z0-9_-]+$"

class CacheException(Exception):
    pass

def json_encode(obj: object) -> dict:
    if isinstance(obj, (bytes, bytearray)):
        return {"_base64": True, "data" : base64.b64encode(obj).decode()}
    raise ValueError(f"No encoding handler for data type {type(obj)}")

def json_decode(obj: dict) -> object:
    if obj.get("_base64") == True:
        return base64.b64decode(obj["data"])
    return obj

class Cache:
    def __init__(self, cache_path: str=None, encryption_key: bytes=None):
        self.cache_path = cache_path
        self.cache_dir = tempfile.mkdtemp()
        self.cache = {}
        self.closed = False
        self.encryptor = Fernet(encryption_key) if encryption_key is not None else None

        if self.cache_path is not None and os.path.isfile(self.cache_path):
            p = subprocess.run(["tar", "-C", self.cache_dir, "-xzf", self.cache_path])
            if p.returncode != 0:
                shutil.rmtree(self.cache_dir)
                raise CacheException("Error extracting cache")

            if os.path.isfile(os.path.join(self.cache_dir, "cache.yaml")):
                with open(os.path.join(self.cache_dir, "cache.yaml")) as f:
                    self.cache = yaml.safe_load(f)

        if not isinstance(self.cache, dict):
            self.cache = {}

    def close(self) -> None:
        self.closed = True
        if self.cache_path is not None:
            with open(os.path.join(self.cache_dir, "cache.yaml"), "w") as f:
                yaml.dump(self.cache, f, default_flow_style=False)
            
            if not os.path.isdir(os.path.dirname(self.cache_path)):
                os.makedirs(os.path.dirname(self.cache_path))
            p = subprocess.run(["tar", "-C", self.cache_dir, "-czf", self.cache_path, "."])
            
            shutil.rmtree(self.cache_dir)
            if p.returncode != 0:
                raise CacheException("Error compressing cache")
        else:
            shutil.rmtree(self.cache_dir)


    def get_file(self, key: str) -> typing.List[bytes]:
        if not re.match(KEY_EXPR, key):
            raise CacheException(f"Invalid cache key: '{key}'")

        if os.path.isfile(os.path.join(self.cache_dir, key)):
            with open(os.path.join(self.cache_dir, key), "rb") as f:
                data = f.read()
                if self.encryptor is not None:
                    data = self.encryptor.decrypt(data)
                return json.loads(data, object_hook=json_decode)

    def put_file(self, key: str, data: typing.List[bytes]) -> None:
        if not re.match(KEY_EXPR, key):
            raise CacheException(f"Invalid cache key: '{key}'")
        
        with open(os.path.join(self.cache_dir, key), "wb") as f:
            _data = json.dumps(data, default=json_encode).encode()
            if self.encryptor is not None:
                _data = self.encryptor.encrypt(_data)
            f.write(_data)

    def get_entry(self, key: str) -> str:
        if not re.match(KEY_EXPR, key):
            raise CacheException(f"Invalid cache key: '{key}'")
        
        return self.cache.get(key)
    
    def put_entry(self, key: str, data: str) -> None:
        if not re.match(KEY_EXPR, key):
            raise CacheException(f"Invalid cache key: '{key}'")

        self.cache[key] = data