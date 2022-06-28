import hashlib
import typing

from src.loadable import Loadable
from src.context import WatchContext
from src.cache import Cache

class MatchException(Exception):
    pass

class Match(Loadable):
    def match(self, ctx: WatchContext, data: typing.List[bytes]) -> bool:
        raise MatchException("Not Implemented")

class CacheMatch(Match):
    """
    CacheMatch returns True when the key:data paid does *not* exist in the cache
    """
    def match(self, ctx: WatchContext, data: typing.List[bytes]) -> bool:
        cache: Cache = ctx.variables["cache"]

        key_digest = ctx.variables["key"]
        data_digest = hashlib.sha256()
        for datum in data:
            data_digest.update(datum)
        data_digest = data_digest.hexdigest()

        if cache.get_entry(key_digest) != data_digest:
            cache.set_entry(key_digest, data_digest)
            return True
        return False
