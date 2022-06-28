import os

class Cache:
    def __init__(self, cache_path):
        if os.path.isfile(cache_path):
            # extract tarfile
            pass
        self.cache = {}

    def get_file(self, key):
        pass

    def get_entry(self, key: str) -> str:
        return self.cache.get(key)
    
    def set_entry(self, key: str, data: str) -> None:
        self.cache[key] = data