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

# TODO:
#   Implement the type typing.List[bytes|typing.List[bytes]] as a custom type for `run_all` methods
#   Perform a final check in `DataWatch.select_data` to ensure the final type is typing.List[bytes]
#  _OR_
#   Should there be a `filter` method to perform the filtering that could be implemented to avoid the above change?

class SelectorException(Exception):
    pass

class Selector(Loadable):
    default_key = "value"
    keys = {
        "value" : (type_none_or_type(str), None),
        "input" : (type_none_or_type(str), None), # The variable to use as input overriding the original data
        "store" : (type_none_or_type(str), None), # Store the result in a variable and pass through the original data
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        raise Exception("Not Implemented")

    def run_all(self, ctx: Context, data:typing.List[bytes]) -> typing.List[bytes]:
        # Run the modifier over each datum recording the result
        _data = []
        for datum in data:
            result = self.run(ctx, datum)
            if len(result) > 0:
                _data.extend(result)
        return _data
    
    # API contract for all selectors
    def execute(self, ctx: Context, data:typing.List[bytes]) -> typing.List[bytes]:
        _data = data
        if self.input is not None:
            _data = ctx.get_variable(self.input)
            if not isinstance(_data, list):
                _data = [_data]

        result = self.run_all(ctx, _data)
        # Ensure correct typing from the selectors
        if not isinstance(result, list) or any([not isinstance(x, bytes) for x in result]):
            raise SelectorException(f"Invalid result from {self.__class__.__name__}: {result}")
        
        # Debug print the result
        if logger.level <= logging.DEBUG:
            _result = "<empty>"
            if len(result):
                try:
                    _result = "".join(["\n\t" + repr(x) for x in result])
                except UnicodeDecodeError:
                    _result = "\n\t" + repr(result)
            logger.debug(f"{self.__class__.__name__}: output: {_result}")

        if self.store is not None:
            ctx.push_variable(self.store, result)
            # When a result is stored, the original input data should be passed though
            return data
        return result

class SubSelector(Selector):
    default_key = "value"
    keys = {
        "value" : (type_list_of_type(dict), None),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selectors = [Selector.load(**x) for x in self.value]

    def run_all(self, ctx: Context, data:typing.List[bytes]) -> typing.List[bytes]:
        _data = []
        for datum in data:
            datum = [datum]
            for selector in self.selectors:
                datum = selector.run_all(ctx, datum)
            _data.extend(datum)
            
        # Ensure correct typing from the sub selectors
        if any([not isinstance(x, bytes) for x in _data]):
            raise SelectorException(f"Invalid result from {self.__class__.__name__}: {_data}")
        return _data

class RegexSelector(Selector):
    default_key = "regex"
    keys = {
        "regex" : (str, ".*"),
        "all" : (bool, False)
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        results = []
        for m in re.finditer(self.regex.encode(), data):
            # Return as a json dictionary if named groups are used
            if m.groupdict():
                results.append(json.dumps({k: (v.decode() if v else None) for k, v in m.groupdict().items()}).encode())
            # Otherwise return as a list
            else:
                if len(m.groups()) == 0:
                    results.append(m.group())
                else:
                    results.extend(m.groups())
        
            if not self.all:
                break
        return results

class JqSelector(Selector):
    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        j = json.loads(data)
        output_lines = []
        for line in jq.compile(self.value).input(j).all():
            if isinstance(line, str):
                output_lines.append(line.encode())
            else:
                output_lines.append(json.dumps(line).encode())
        return output_lines

class HTMLSelector(Selector):
    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        soup = BeautifulSoup(data, "html.parser")
        return [str(x).encode() for x in soup.select(self.value)]

class XmlSelector(Selector):
    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        soup = BeautifulSoup(data, "lxml-xml")
        return [str(x).encode() for x in soup.select(self.value)]

class DecodeSelector(Selector):
    default_key = "encoding"
    keys = {
        "encoding" : (str, str)
    }
    ENCODING_HTML = "html"

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        if self.encoding == self.ENCODING_HTML:
            return [html.unescape(data.decode()).encode()]
        raise Exception(f"Unknown encoding {self.encoding}")

class BytesSelector(Selector):
    default_key = "end"
    keys = {
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        return [data[self.start:self.end]]

class LinesSelector(Selector):
    keys = {
        "keepends" : (bool, False),
        "html" : (bool, False)
    }
    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        if html:
            data = re.sub(b'<(br\s*/|/p)>', b'<\\1>\n', data)
            
        return data.splitlines(keepends=self.keepends)

class SplitSelector(Selector):
    """
    Split a byte string into a list of byte strings using a separator
    """
    keys = {
        "sep" : (str, ","),
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        bsep = self.sep.encode()
        return data.split(bsep)[self.start:self.end]

class JoinSelector(Selector):
    """
    Join either a list of bytes with a separator
    """
    default_key = "sep"
    keys = {
        "sep" : (str, ",")
    }
    
    def run_all(self, ctx: Context, data: typing.List[bytes]) -> typing.List[bytes]:
        if len(data) == 0:
            return []
        return [self.sep.encode().join(data)]

class StripSelector(Selector):
    """
    Strip leading and trailing characters from a byte string
    """
    default_key = "chars"
    keys = {
        "chars" : (str, "\r\n\t "),
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        return [data.strip(self.chars.encode())]

class StripTagsSelector(Selector):
    """
    Strip HTML tags from a byte string
    """
    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        return [re.sub(b'<[^>]+>', b'', data)]

class ReplaceSelector(Selector):
    """
    Replace a regex pattern with a byte string
    """
    default_key = "regex"
    keys = {
        "regex" : (str, ".*"),
        "replacement" : (str, "")
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        return [re.sub(self.regex.encode(), self.replacement.encode(), data)]

class SliceSelector(Selector):
    """
    Slice a list of bytes
    """
    default_key = "end"
    keys = {
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run_all(self, ctx: Context, data:typing.List[bytes]) -> typing.List[bytes]:
        return data[self.start:self.end]

class PickSelector(Selector):
    """
    Pick indexed elements from a list of bytes
    """
    default_key = "index"
    keys = {
        "index" : (type_list_of_type(int), [])
    }

    def run_all(self, ctx: Context, data:typing.List[bytes]) -> typing.List[bytes]:
        if len(data) == 0:
            return []
        return [x for i, x in enumerate(data) if i in self.index]

class NewSelector(Selector):
    """
    Select new data from a list of bytes that is not in the cache
    """
    default_key = "key"
    keys = {
        "key" : (type_none_or_type(str), None),
    }

    def run_all(self, ctx: Context, data:typing.List[bytes]) -> typing.List[bytes]:
        cache: Cache = ctx.get_variable("cache")

        hash_key = ctx.expand_context(self.key) if self.key is not None else f"{self.hash}-selector-new"
        logger.debug(f"{self.__class__.__name__}: cache key {hash_key}")

        old_set = set(cache.get_file(hash_key))

        # Iterate instead of `difference` to preserve order
        new_entries = []
        for datum in data:
            if not datum in old_set:
                new_entries.append(datum)
        
        cache.put_file(hash_key, list(old_set.union(new_entries)))
        return new_entries
    
class SinceSelector(Selector):
    """
    Select data from a list of bytes up until a previously observed datum
    """
    default_key = "key"
    keys = {
        "key" : (type_none_or_type(str), None),
    }

    def run_all(self, ctx: Context, data:typing.List[bytes]) -> typing.List[bytes]:
        cache: Cache = ctx.get_variable("cache")

        hash_key = ctx.expand_context(self.key) if self.key is not None else f"{self.hash}-selector-since"
        logger.debug(f"{self.__class__.__name__}: cache key {hash_key}")

        index = None
        since = cache.get_entry(hash_key)
        if since is not None:
            for i, datum in enumerate(data):
                if hashlib.sha256(datum).hexdigest() == since:
                    index = i
                    break
        
        _data = data[:index]
        if len(_data) > 0:
            cache.put_entry(hash_key, hashlib.sha256(_data[0]).hexdigest())
        return _data

