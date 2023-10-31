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
from src.loadable import Loadable, type_none_or_type

logger = logging.getLogger(__name__)

class SelectorException(Exception):
    pass

class Selector(Loadable):
    default_key = "value"
    keys = {
        "value" : (type_none_or_type(str), None),
        "input" : (type_none_or_type(str), None),
        "store" : (type_none_or_type(str), None)
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        raise Exception("Not Implemented")

    def run_all(self, ctx: Context, data:typing.List[bytes]) -> typing.List[bytes]:
        # Run the modifier over each datum, and flatpack the result
        _data = []
        for datum in data:
            result = self.run(ctx, datum)
            _data.extend([x for x in result if x is not None and len(x) > 0])
        return _data
    
    def execute(self, ctx: Context, data:typing.List[bytes]) -> typing.List[bytes]:
        _data = data
        if self.input is not None:
            _data = ctx.get_variable(self.input)
            if not isinstance(_data, list):
                _data = [_data]

        result = self.run_all(ctx, _data)
        _result = "<empty>"
        if len(result):
            try:
                _result = "\n\t" + b'\n\t'.join(result).decode()
            except UnicodeDecodeError:
                _result = "\n\t" + repr(result)
        logger.debug(f"{self.__class__.__name__}: output: {_result}")

        if self.store is not None:
            ctx.push_variable(self.store, result)
            # When a result is stored, the original input data should be passed though
            return data
        return result

class RegexSelector(Selector):
    default_key = "regex"
    keys = {
        "regex" : (str, ".*")
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        m = re.search(self.regex.encode(), data)
        if m is None:
            return []
        
        # Return as a json dictionary if named groups are used
        if m.groupdict():
            return [json.dumps({k: v.decode() for k, v in m.groupdict().items()}).encode()]

        # Otherwise return as a list
        if len(m.groups()) == 0:
            return [m.group()]
        return list(m.groups())

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
        "keepends" : (bool, False)
    }
    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        return data.splitlines(keepends=self.keepends)

class SplitSelector(Selector):
    keys = {
        "sep" : (str, ","),
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        bsep = self.sep.encode()
        return data.split(bsep)[self.start:self.end]

class StripSelector(Selector):
    default_key = "chars"
    keys = {
        "chars" : (str, "\r\n\t "),
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        return [data.strip(self.chars.encode())]

class StripTagsSelector(Selector):
    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        return [re.sub(b'<[^>]+>', b'', data)]

class ReplaceSelector(Selector):
    default_key = "regex"
    keys = {
        "regex" : (str, ".*"),
        "replacement" : (str, "")
    }

    def run(self, ctx: Context, data:bytes) -> typing.List[bytes]:
        return [re.sub(self.regex.encode(), self.replacement.encode(), data)]

class SliceSelector(Selector):
    default_key = "end"
    keys = {
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run_all(self, ctx: Context, data:typing.List[bytes]) -> list:
        return data[self.start:self.end]

class NewSelector(Selector):
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

