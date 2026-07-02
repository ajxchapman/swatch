from __future__ import annotations
import hashlib
import html
import json
import logging
import re
import typing

import jq
from bs4 import BeautifulSoup
from lxml import etree

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

    def clone(self, value:typing.Optional[bytes]=None, vars:typing.Optional[dict]=None) -> SelectorItem:
        # Note: an explicit empty value (e.g. b'') must be preserved, so test
        # against None rather than truthiness.
        return SelectorItem(self.value if value is None else value, {**self.vars, **(vars or {})})

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
            if isinstance(line, dict):
                # Ensure all vars values are encoded
                vars = {k: str(v).encode() for k, v in line.items()}
                results.append(item.clone(vars=vars))
            elif isinstance(line, str):
                results.append(item.clone(line.encode()))
            else:
                # Coerce any other scalar (int, float, bool, None, list) to bytes
                results.append(item.clone(str(line).encode()))
        return results

class HTMLSelector(Selector):
    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        soup = BeautifulSoup(item.value, "html.parser")
        return [item.clone(str(x).encode()) for x in soup.select(self.value)]

class XmlSelector(Selector):
    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        soup = BeautifulSoup(item.value, "lxml-xml")
        return [item.clone(str(x).encode()) for x in soup.select(self.value)]

class XPathSelector(Selector):
    """
    Select nodes with XPath and (optionally) extract named sub-values into vars:

        - xpath: '//item'
          vars:
            title: 'title/text()'
            summary: 'description/text()'
            link: 'link/text()'

    XML namespaces are stripped after parsing so Atom and RSS feeds can be
    queried with plain, prefix-free paths (e.g. `//item/title` works even when
    the feed declares a default namespace). Each `vars` entry is a relative
    XPath that returns text (`.../text()`) or an attribute (`.../@href`); the
    first result is stored under that name. With no `vars`, the selected nodes
    are returned as items - serialized XML for elements, or the string value
    for text()/@attribute selects.
    """
    default_key = "select"
    keys = {
        "select" : (str, "."),
        "vars" : (dict, dict),
    }

    @staticmethod
    def _to_bytes(value: typing.Any) -> typing.Optional[bytes]:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode()
        if isinstance(value, etree._Element):
            return etree.tostring(value)
        return str(value).encode()

    def run(self, ctx: Context, item:SelectorItem) -> typing.List[SelectorItem]:
        root = etree.fromstring(item.value, parser=etree.XMLParser(recover=True))
        if root is None:
            return []

        # Strip namespaces so feed-agnostic paths work across RSS and Atom
        for el in root.iter():
            if isinstance(el.tag, str) and "}" in el.tag:
                el.tag = el.tag.split("}", 1)[1]
        etree.cleanup_namespaces(root)

        results = []
        for node in root.xpath(self.select):
            if isinstance(node, etree._Element):
                extracted = {}
                for name, path in self.vars.items():
                    found = node.xpath(path)
                    extracted[name] = self._to_bytes(found[0]) if found else None
                results.append(item.clone(etree.tostring(node), extracted))
            else:
                # text()/@attribute selects yield strings rather than elements
                results.append(item.clone(self._to_bytes(node)))
        return results

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
        if self.html:
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

class TextToColsSelector(Selector):
    """
    """
    default_key = "titles"
    keys = {
        "titles" : (type_list_of_type(str), []),
    }

    def run_all(self, ctx: Context, items:typing.List[SelectorItem]) -> typing.List[SelectorItem]:
        r = SelectorItem(b"", {})
        for i, t in enumerate(self.titles):
            if i < len(items):
                r.vars[t] = items[i].value
            else:
                r.vars[t] = None
        return [r]
            

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
        "key" : (type_none_or_type(str), None),
    }
    type = None

    def item_key(self, item: SelectorItem) -> typing.Optional[bytes]:
        """
        The identity bytes used to recognise an item across runs.

        When a `key` var name is configured, the item must supply it - a missing
        (or None) value returns None to signal malformed data (e.g. an API error
        object parsed into empty items) rather than silently hashing the wrong
        value. Without a configured key the item's value is hashed.
        """
        if self.key is not None:
            value = item.vars.get(self.key)
            if value is None:
                return None
        else:
            value = hashlib.sha256(item.value).hexdigest()
        return value.encode() if isinstance(value, str) else value

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
        keys = [self.item_key(item) for item in items]

        # In keyed mode a missing key means the batch is malformed (e.g. an API
        # error object parsed into empty items). Refuse it so we neither emit
        # bogus results nor overwrite the cached position, which would otherwise
        # cause the whole backlog to be re-reported on the next good response.
        if any(key is None for key in keys):
            logger.warning(f"{self.__class__.__name__}: item(s) missing key '{self.key}', skipping batch")
            return []

        index = None
        last_value = self.get_cached_data(ctx)
        if last_value is not None:
            for i, key in enumerate(keys):
                if key == last_value:
                    index = i
                    break

        _items = items[:index]
        if len(_items) > 0:
            self.put_cached_data(ctx, keys[0])
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