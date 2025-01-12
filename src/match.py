import hashlib
import logging
import re
import typing

from src.loadable import Loadable, type_none_or_type
from src.context import Context
from src.cache import Cache
from src.template import template_render
from src.selector import SelectorItem

logger = logging.getLogger(__name__)

class MatchException(Exception):
    pass

class Match(Loadable):
    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        raise MatchException("Not Implemented")

class CacheMatch(Match):
    """
    CacheMatch returns True when the key:data pair does *not* exist in the cache
    """

    keys = {
        "key" : (type_none_or_type(str), None),
        "empty" : (bool, False) # Consider an empty data array
    }
    default_key = "key"

    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        if not self.empty:
            if len(data) == 0:
                logger.debug(f"CacheMatch: Empty data, returning False")
                return False

        cache: Cache = ctx.get_variable("cache")

        hash_key = ctx.expand_context(self.key) if self.key is not None else f"{self.hash}-match"
        logger.debug(f"{self.__class__.__name__}: cache key {hash_key}")
        if not cache.has_entry(hash_key):
            cache.put_entry(hash_key, True)
            logger.debug(f"CacheMatch: Cache miss, returning True")
            return True
        logger.debug(f"CacheMatch: Cache hit, returning False")
        return False

class CondMatch(Match):
    keys = {
        "operator" : (str, None),
        "value" : (lambda x: x, None),
        "comparitor" : (str, "{{ data }}")
    }
    default_key = "value"
    operators = {"eq" : "eq", "==" : "eq", "neq" : "neq", "!=" : "neq", "lt" : "lt", "<" : "lt", "lte" : "lte", "<=" : "lte", "gt" : "gt", ">" : "gt", "gte" : "gte", ">=" : "gte"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        m = re.match("(?:(.*)\s+)?(eq|==|neq|!=|lt|<|lte|<=|gt|>|gte|>=)\s+(.*)", self.value)
        if m is not None:
            self.comparitor, self.operator, self.value = m.groups()
            self.comparitor = self.comparitor or self.keys["comparitor"][1]
        
        self.operator = self.operators.get(self.operator)
        if self.operator is None:
            raise MatchException(f"Unknown operator '{self.operator}")

    def match(self, ctx: Context, items: typing.List[SelectorItem]) -> bool:
        if len(items) != 1:
            raise MatchException("CondMatch can only operate on one item")
        
        item = items[0]
        c1 = template_render(self.comparitor, ctx, data=item.value)
        c2 = template_render(self.value, ctx, data=item.value)

        logger.debug(f"CondMatch: {self.comparitor} {self.operator} {self.value}")
        logger.debug(f"CondMatch: {c1} {self.operator} {c2}")
        logger.debug(ctx.frames)

        if self.operator not in ["eq", "neq"]:
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
        elif self.operator == "neq":
            return c1 != c2
        return c1 == c2

class NoneMatch(Match):
    """
    NoneMatch return True always
    """

    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        return True