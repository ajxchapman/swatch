from __future__ import annotations
import hashlib
import html
import json
import logging
import re
import typing

import jq
from bs4 import BeautifulSoup

from src.cache import Cache
from src.context import Context
from src.loadable import Loadable, type_none_or_type, type_list_of_type

logger = logging.getLogger(__name__)


class SelectorException(Exception):
    pass

class SelectorItem():
    def __init__(self, value:bytes, vars:typing.Optional[dict]=None):
        self.value:bytes = value
        self.vars:dict = vars or dict()

    def clone(self, value:typing.Optional[bytes]=None, vars:typing.Optional[dict]={}) -> SelectorItem:
        return SelectorItem(value or self.value, {**self.vars, **vars})

    def encode(self) -> dict:
        return {"value": self.value, "vars": self.vars}
    
    @classmethod
    def decode(cls, data:dict) -> SelectorItem:
        return cls(data["value"], data["vars"])
    
    def __repr__(self):
        return f"<SelectorItem value={repr(self.value)}, vars={repr(self.vars)}>"
    
    def __hash__(self) -> int:
        hash_value = hash(self.__class__.__name__)
        hash_value ^= hash(self.value)
        for k, v in self.vars.items():
            hash_value ^= hash(k) ^ hash(v)
        return hash_value
    
    def __eq__(self, other:SelectorItem) -> bool:
        return hash(self) == hash(other)

class Selector(Loadable):
    default_key = "value"
    keys = {
        "value" : (type_none_or_type(str), None),
        "input" : (type_none_or_type(str), None), # The variable to use as input overriding the original data
        "store" : (type_none_or_type(str), None), # Store the result in a variable and pass through the original data
    }

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        raise Exception("Not Implemented")

    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        # Run the modifier over each datum recording the result
        _data = []
        for datum in items:
            result = self.run(ctx, datum)
            if len(result) > 0:
                _data.extend(result)
        return _data
    
    # API contract for all selectors
    def execute(self, ctx: Context, data:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        _data = data
        if self.input is not None:
            _data = ctx.get_variable(self.input)
            if not isinstance(_data, list):
                _data = [_data]

        results = self.run_all(ctx, _data)

        # Ensure correct typing from the selectors
        if not isinstance(results, list) or any([not isinstance(x, SelectorItem) for x in results]):
            raise SelectorException(f"Invalid result from {self.__class__.__name__}: {results}")
        
        # Debug print the result
        if logger.level <= logging.DEBUG:
            _result = "<empty>"
            if len(results):
                try:
                    _result = "".join(["\n\t" + repr(x) for x in results])
                except UnicodeDecodeError:
                    _result = "\n\t" + repr(results)
            logger.debug(f"{self.__class__.__name__}: output: {_result}")

        if self.store is not None:
            ctx.push_variable(self.store, results)
            # When a result is stored, the original input data should be passed though
            return data
        return results

class SubSelector(Selector):
    default_key = "value"
    keys = {
        "value" : (type_list_of_type(dict), None),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selectors = [Selector.load(**x) for x in self.value]

    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        # TODO: Should this call execute instead of run_all?
        _items = []
        for item in items:
            item = [item]
            for selector in self.selectors:
                item = selector.run_all(ctx, item)
            _items.extend(item)
            
        # Ensure correct typing from the sub selectors
        if any([not isinstance(x, SelectorItem) for x in _items]):
            raise SelectorException(f"Invalid result from {self.__class__.__name__}: {_items}")
        return _items

class RegexSelector(Selector):
    default_key = "regex"
    keys = {
        "regex" : (str, ".*"),
        "all" : (bool, False)
    }

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        results = []
        for m in re.finditer(self.regex.encode(), item.value):
            # If named groups are used add the values to data.vars
            if m.groupdict():
                results.append(item.clone(m.group(), m.groupdict()))
            else:
                # If there are no groups, just add the match
                if len(m.groups()) == 0:
                    results.append(item.clone(m.group()))
                # Otherwise extend the result set with the matched groups
                else:
                    results.extend([item.clone(x) for x in m.groups()])
            if not self.all:
                break
        return results

class JqSelector(Selector):
    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        j = json.loads(item.value)
        results = []
        for line in jq.compile(self.value).input(j).all():
            if isinstance(line, str):
                results.append(item.clone(line.encode()))
            else:
                # Ensure all vars values are encoded
                vars = {k: str(v).encode() for k, v in line.items()}
                results.append(item.clone(vars=vars))
        return results

class HTMLSelector(Selector):
    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        soup = BeautifulSoup(item.value, "html.parser")
        return [item.clone(str(x).encode()) for x in soup.select(self.value)]

class XmlSelector(Selector):
    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        soup = BeautifulSoup(item.value, "lxml-xml")
        return [item.clone(str(x).encode()) for x in soup.select(self.value)]

class DecodeSelector(Selector):
    default_key = "encoding"
    keys = {
        "encoding" : (str, str)
    }
    ENCODING_HTML = "html"

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        if self.encoding == self.ENCODING_HTML:
            return [item.clone(html.unescape(item.value.decode()).encode())]
        raise Exception(f"Unknown encoding {self.encoding}")

class BytesSelector(Selector):
    default_key = "end"
    keys = {
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        return [item.clone(item.value[self.start:self.end])]

class LinesSelector(Selector):
    keys = {
        "keepends" : (bool, False),
        "html" : (bool, False)
    }

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        value = item.value
        if html:
            value = re.sub(rb'<(br\s*/|/p)>', b'<\\1>\n', value)
            
        return [item.clone(x) for x in value.splitlines(keepends=self.keepends)]

class SplitSelector(Selector):
    """
    Split a byte string into a list of byte strings using a separator
    """
    default_key = "sep"
    keys = {
        "sep" : (str, ","),
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        bsep = self.sep.encode()
        return [item.clone(x) for x in item.value.split(bsep)[self.start:self.end]]

class JoinSelector(Selector):
    """
    Join either a list of bytes with a separator
    """
    default_key = "sep"
    keys = {
        "sep" : (str, ",")
    }
    
    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        if len(items) == 0:
            return []
        # Clone the first item in data and join the remaining item values
        return [items[0].clone(self.sep.encode().join([x.value for x in items]))]

class StripSelector(Selector):
    """
    Strip leading and trailing characters from a byte string
    """
    default_key = "chars"
    keys = {
        "chars" : (str, "\r\n\t "),
    }

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        return [item.clone(item.value.strip(self.chars.encode()))]

class StripTagsSelector(Selector):
    """
    Strip HTML tags from a byte string
    """
    default_key = "replacement"
    keys = {
        "replacement" : (str, ""),
    }

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        return [item.clone(re.sub(b'(?:<[^>]+>)+', self.replacement.encode(), item.value))]

class ReplaceSelector(Selector):
    """
    Replace a regex pattern with a byte string
    """
    default_key = "regex"
    keys = {
        "regex" : (str, ".*"),
        "replacement" : (str, "")
    }

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        return [item.clone(re.sub(self.regex.encode(), self.replacement.encode(), item.value))]

class SliceSelector(Selector):
    """
    Slice a list of SelectorItems
    """
    default_key = "end"
    keys = {
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        return items[self.start:self.end]

class PickSelector(Selector):
    """
    Pick indexed items from a list of SelectorItems
    """
    default_key = "index"
    keys = {
        "index" : (type_list_of_type(int), [])
    }

    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        if len(items) == 0:
            return []
        return [x for i, x in enumerate(items) if i in self.index]


class FormatSelector(Selector):
    """
    Format a string with the vars values
    """
    default_key = "format"
    keys = {
        "format" : (str, ""),
        "var" : (type_none_or_type(str), None)
    }

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        ctx.push_variable("vars", item.vars)
        value = ctx.expand_context(self.format).encode()
        ctx.pop_variable("vars")
        if self.var is not None:
            return [item.clone(vars={self.var: value})]
        return [item.clone(value)]

class CacheSelector(Selector):
    default_key = "cache_key"
    keys = {
        "cache_key" : (type_none_or_type(str), None),
        "key" : (type_none_or_type(str), "key"),
    }
    type = None

    def get_cached_data(self, ctx: Context) -> typing.Any:
        cache: Cache = ctx.get_variable("cache")
        hash_key = ctx.expand_context(self.cache_key) if self.cache_key is not None else f"{self.hash}-selector-cache-{self.__class__.__name__.lower()}"

        # Return the cached file cast as type or a default value for the CacheSelector type
        data = cache.get_file(hash_key)
        logger.log(logging.DEV, f"{self.__class__.__name__} get_cached_values: cache key {hash_key}: {data}")
        if data:
            if self.type:
                return self.type(data)
            return data
        return self.type() if callable(self.type) else None
    
    def put_cached_data(self, ctx: Context, data: typing.Any) -> None:
        cache: Cache = ctx.get_variable("cache")
        hash_key = ctx.expand_context(self.cache_key) if self.cache_key is not None else f"{self.hash}-selector-cache-{self.__class__.__name__.lower()}"
        logger.log(logging.DEV, f"{self.__class__.__name__} put_cached_values: cache key {hash_key}: {data}")
        cache.put_file(hash_key, data)

class NewSelector(CacheSelector):
    """
    Select new items from a list of SelectorItems that is not in the cache
    """
    type = set

    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        cached_set = self.get_cached_data(ctx)

        # Iterate instead of `difference` to preserve order
        new_items = []
        for item in items:
            key = item.vars.get(self.key, hashlib.sha256(item.value).hexdigest())
            # TODO: Is this the best way to coerce the key to bytes?
            if isinstance(key, str):
                key = key.encode()

            if not key in cached_set:
                new_items.append(item)
                cached_set.add(key)
        
        self.put_cached_data(ctx, list(cached_set))
        return new_items

class SinceSelector(CacheSelector):
    """
    Select items from a list of SelectorItems up until a previously observed item
    """

    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        index = None
        last_value = self.get_cached_data(ctx)
        if last_value is not None:
            for i, item in enumerate(items):
                item_value = item.vars.get(self.key, hashlib.sha256(item.value).hexdigest())
                # TODO: Is this the best way to coerce the key to bytes?
                if isinstance(item_value, str):
                    item_value = item_value.encode()
                
                if item_value == last_value:
                    index = i
                    break
        
        _items = items[:index]
        if len(_items) > 0:
            item_value = _items[0].vars.get(self.key, hashlib.sha256(_items[0].value).hexdigest())
            # TODO: Is this the best way to coerce the item_value to bytes?
            if isinstance(item_value, str):
                item_value = item_value.encode()
            self.put_cached_data(ctx, item_value)
        return _items

class DictstoreSelector(CacheSelector):
    """
    Store items in a dict
    """
    type = dict

    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        cached_dict = self.get_cached_data(ctx)
        for item in items:
            key = item.vars.get(self.key, hashlib.sha256(item.value).hexdigest().encode()).decode()
            cached_dict[key] = item.encode()
        self.put_cached_data(ctx, cached_dict)
        return items
    
class DictloadSelector(CacheSelector):
    """
    Load items from a dict
    """
    keys = {
        "filter" : (bool, False),
    }
    type = dict

    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        cached_dict = self.get_cached_data(ctx)
        results = []
        for item in items:
            if not self.filter:
                results.append(item)
            key = item.vars.get(self.key, hashlib.sha256(item.value).hexdigest().encode()).decode()
            if key in cached_dict:
                if self.filter:
                    results.append(item)
                results[-1] = item.clone(vars=cached_dict[key]["vars"])
        return results