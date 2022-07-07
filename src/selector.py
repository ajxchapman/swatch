import hashlib
import json
import re
import typing

import jq
from bs4 import BeautifulSoup

from src.loadable import Loadable

class SelectorException(Exception):
    pass

class Selector(Loadable):
    default_key = "value"
    keys = {
        "value" : (str, None)
    }

    def run_all(self, data:typing.List[bytes]) -> typing.List[bytes]:
        # Run the modifier over each datum, and flatpack the result
        outdata = []
        for datum in data:
            result = self.run(datum)
            outdata.extend([x for x in result if x is not None and len(x) > 0])
        return outdata
    
    def run(self, data:bytes) -> typing.List[bytes]:
        raise Exception("Not Implemented")

class RegexSelector(Selector):
    default_key = "regex"
    keys = {
        "regex" : (str, ".*")
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        m = re.search(self.regex.encode(), data)
        if m is None:
            return [b'']
        if len(m.groups()) == 0:
            return [m.group()]
        return list(m.groups())

class JqSelector(Selector):
    def run(self, data:bytes) -> typing.List[bytes]:
        j = json.loads(data)
        output_lines = []
        for line in jq.compile(self.value).input(j).all():
            if isinstance(line, str):
                output_lines.append(line.encode())
            else:
                output_lines.append(json.dumps(line).encode())
        return output_lines

class CssSelector(Selector):
    def run(self, data:bytes) -> typing.List[bytes]:
        soup = BeautifulSoup(data, "html.parser")
        return [str(x).encode() for x in soup.select(self.value)]

class BytesSelector(Selector):
    keys = {
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        return [data[self.start:self.end]]

class LinesSelector(Selector):
    keys = {
        "keepends" : (bool, False)
    }
    def run(self, data):
        return data.splitlines(keepends=self.keepends)

class SplitSelector(Selector):
    keys = {
        "sep" : (str, ","),
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        bsep = self.sep.encode()
        return data.split(bsep)[self.start:self.end]

class NewSelector(Selector):
    keys = {
        "key" : (str, None),
        "cache" : (dict, {}) # This references the on disk cache
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        key_digest = hashlib.sha256(self.key.encode()).hexdigest()
        cached_set = set(self.cache.setdefault("elements", {}).setdefault(key_digest, []))

        lines = data.splitlines()
        data_digest = hashlib.sha256(data).hexdigest()
        if not data_digest in cached_set:
            self.cache["elements"][key_digest].append(data_digest)
            return [data]
        return []

class StripSelector(Selector):
    default_key = "chars"
    keys = {
        "chars" : (str, "\r\n\t "),
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        return [data.strip(self.chars.encode())]

class ReplaceSelector(Selector):
    default_key = "regex"
    keys = {
        "regex" : (str, ".*"),
        "replacement" : (str, "")
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        return [re.sub(self.regex.encode(), self.replacement.encode(), data)]

class IndexSelector(Selector):
    keys = {
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run_all(self, data:typing.List[bytes]) -> list:
        return data[self.start:self.end]