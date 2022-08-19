import hashlib
import re
import typing

from src.loadable import Loadable
from src.context import Context
from src.cache import Cache
from src.template import template_render

class MatchException(Exception):
    pass

class Match(Loadable):
    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        raise MatchException("Not Implemented")

class CacheMatch(Match):
    """
    CacheMatch returns True when the key:data paid does *not* exist in the cache
    """
    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        cache: Cache = ctx.get_variable("cache")

        key_digest = ctx.get_variable("hash")
        data_digest = hashlib.sha256()
        for datum in data:
            data_digest.update(datum)
        data_digest = data_digest.hexdigest()

        if cache.get_entry(key_digest) != data_digest:
            cache.put_entry(key_digest, data_digest)
            return True
        return False

class CondMatch(Match):
    keys = {
        "operator" : (str, None),
        "value" : (lambda x: x, None),
        "comparitor" : (str, "{{ data }}")
    }
    default_key = "value"
    operators = {"eq" : "eq", "==" : "eq", "lt" : "lt", "<" : "lt", "lte" : "lte", "<=" : "lte", "gt" : "gt", ">" : "gt", "gte" : "gte", ">=" : "gte"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        m = re.match("(?:(.*)\s+)?(eq|==|lt|<|lte|<=|gt|>|gte|>=)\s+(.*)", self.value)
        if m is not None:
            self.comparitor, self.operator, self.value = m.groups()
            self.comparitor = self.comparitor or self.keys["comparitor"][1]
        
        self.operator = self.operators.get(self.operator)
        if self.operator is None:
            raise MatchException(f"Unknown operator '{self.operator}")

    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        c1 = template_render(self.comparitor, ctx.variables, data=data)
        c2 = template_render(self.value, ctx.variables, data=data)

        if self.operator != "eq":
            try:
                c1 = int(c1)
                c2 = int(c2)
            except (TypeError, ValueError):
                raise MatchException("Less than and Greater than comparisons can only be performed on integer values")
        
        if self.operator == "lt":
            return c1 < c2
        elif self.operator == "lte":
            return c1 <= c2
        elif self.operator == "gt":
            return c1 > c2
        elif self.operator == "gte":
            return c1 >= c2
        return c1 == c2

class NoneMatch(Match):
    """
    NoneMatch return True always
    """

    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        return True