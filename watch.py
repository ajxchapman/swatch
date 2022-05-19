import argparse
import hashlib
import json
import os
import re
import requests
import subprocess
import sys
import typing
import yaml

import jq
from bs4 import BeautifulSoup

def read_cache(filename):
    cache = {}
    if os.path.isfile(filename):
        with open(filename) as f:
            cache = yaml.safe_load(f)
    if not isinstance(cache, dict):
        cache = {}
    cache.setdefault("watches", {})
    return cache

def write_cache(filename, cache):
    with open(filename, "w") as f:
        yaml.dump(cache, f, default_flow_style=False)

def check_in_cache(cache, key, data):
    key_digest = hashlib.sha256(key.encode()).hexdigest()
    data_digest = hashlib.sha256()
    for datum in data:
        data_digest.update(datum)
    data_digest = data_digest.hexdigest()

    # If the key_digest is not previously watched, or the data_digest does not match the cache, alert
    if cache["watches"].get(key_digest) != data_digest:
        cache["watches"][key_digest] = data_digest
        return False
    return True

def alert(message, alert_hook=None):
    if alert_hook is not None:
        data = alert_hook.get("payload", json.dumps({"text" : message})).replace("MESSAGE", json.dumps(message))
        r = requests.request(
            alert_hook.get("method", "POST"),
            alert_hook["url"],
            headers={"content-type" : alert_hook.get("content-type", "application/json")},
            data=data.encode()
        )
    else:
        print(message)

class ModifierException(Exception):
    pass

class WatchException(Exception):
    def __init__(self, key, *args, **kwargs):
        self.key = key
        super().__init__(*args, **kwargs)

class WatchFetchException(WatchException):
    pass

class WatchSelectorException(WatchException):
    pass

class Modifier:
    modifier_classes = None
    modifier_class_keys = None
    default_key = "value"
    keys = {
        "value" : (str, None)
    }

    @classmethod
    def load(cls, **kwargs):
        # Load subclass default keys
        if Modifier.modifier_classes is None:
            Modifier.modifier_classes = {}
            Modifier.modifier_class_keys = {}
            for c in cls.__subclasses__():
                modifier_name = c.__name__.replace(cls.__name__, "").lower()
                Modifier.modifier_classes[modifier_name] = c
                for x in c.__mro__[::-1]:
                    Modifier.modifier_class_keys[modifier_name] = {**Modifier.modifier_class_keys.get(modifier_name, {}), **getattr(x, "keys", {})}

        # Obtain the modifier type either looking for the `type` key, or use the name of the only key if there is only one
        # Allows for definitions such as:
        #   - type: "regex"
        #     value: ".*"
        # Or
        #   - regex: ".*"
        mtype = kwargs.get("type")
        if mtype is not None:
            del kwargs["type"]
        else:
            mtype = next(kwargs.keys().__iter__())
            mvalue = kwargs[mtype]
            del kwargs[mtype]
            kwargs[Modifier.modifier_classes[mtype].default_key] = mvalue
        if mtype is None:
            raise ModifierException("No type for modifier")

        # Initialise modifier from kwargs
        o = Modifier.modifier_classes[mtype]()
        for k, v in Modifier.modifier_class_keys[mtype].items():
            ktype, kdefault = v
            if k in kwargs:
                # Cast as the correct type
                val = kwargs[k] if isinstance(kwargs[k], ktype) else ktype(kwargs[k])
                setattr(o, k, val)
            else:
                setattr(o, k, kdefault)
        return o

    def run(self, data:bytes) -> typing.List[bytes]:
        raise Exception("Not Implemented")

class RegexModifier(Modifier):
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

class JqModifier(Modifier):
    def run(self, data:bytes) -> typing.List[bytes]:
        j = json.loads(data)
        output_lines = []
        for line in jq.compile(self.value).input(j).all():
            if isinstance(line, str):
                output_lines.append(line.encode())
            else:
                output_lines.append(json.dumps(line).encode())
        return output_lines

class CssModifier(Modifier):
    def run(self, data:bytes) -> typing.List[bytes]:
        soup = BeautifulSoup(data, "html.parser")
        return [str(x).encode() for x in soup.select(self.value)]

class BytesModifier(Modifier):
    keys = {
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        return [data[self.start:self.end]]

class LinesModifier(Modifier):
    keys = {
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, data):
        return data.splitlines(keepends=True)[self.start:self.end]

class NewModifier(Modifier):
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

class SplitModifier(Modifier):
    keys = {
        "sep" : (str, ","),
        "start" : (int, 0),
        "end" : (int, None)
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        bsep = self.sep.encode()
        return [bsep.join(data.split(bsep)[self.start:self.end])]

class StripModifier(Modifier):
    default_key = "chars"
    keys = {
        "chars" : (str, "\t "),
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        return [data.strip(self.chars.encode())]

class ReplaceModifier(Modifier):
    default_key = "regex"
    keys = {
        "regex" : (str, ".*"),
        "replacement" : (str, "")
    }

    def run(self, data:bytes) -> typing.List[bytes]:
        return [re.sub(self.regex.encode(), self.replacement.encode(), data)]


class Watch:
    keys = {
        "selectors" : [],
        "output" : [],
        "comment" : ""
    }

    @classmethod
    def load(cls, object_definitions):
        # Load default key values from the Watch subclasses
        decoders = {}
        class_keys = {}
        for c in cls.__subclasses__():
            decoders[c.__name__.replace(cls.__name__, "").lower()] = c
            for x in c.__mro__[::-1]:
                class_keys[c.__name__] = {**class_keys.get(c.__name__, {}), **getattr(x, "keys", {})}

        # For each of the input object_definitions, find the correct class and decode it using default values where not provided
        _watchers = []
        for object_definition in object_definitions:
            for object_type, wclass in decoders.items():
                if object_type in object_definition:
                    _watchers.append(wclass.decode(**{**class_keys[wclass.__name__], **object_definition, "key" : object_definition[object_type]}))
                    break
        return _watchers

    @classmethod
    def decode(cls, **kwargs):
        # Basic decode method to set object attributes from arguments
        o = cls()
        for key, value in kwargs.items():
            setattr(o, key, value)
        return o

    def apply_modifiers(self, modifiers, data, **kwargs):
        for modifier_data in modifiers:
            try:
                modifier = Modifier.load(**modifier_data, **kwargs)
            except ModifierException as e:
                raise WatchSelectorException(self.key, f"Error parsing modifiers") from e

            # Run the modifier over each datum, and flatpack the result
            outdata = []
            for datum in data:
                result = modifier.run(datum)
                outdata.extend([x for x in result if x is not None and len(x) > 0])
            data = outdata
        return data

    def fetch(self, *args, **kwargs):
        raise WatchFetchException(self.key, "Not implemented")

    def in_cache(self, cache, verbose=False):
        try:
            selected_data = self.apply_modifiers(self.selectors, [self.fetch()], key=self.key, cache=cache)
        except Exception as e:
            raise WatchSelectorException(self.key, "Exception selecting data") from e

        try:
            self.output_data = self.apply_modifiers(self.output, selected_data, key=self.key, cache=cache) if len(self.output) else None
        except Exception as e:
            raise WatchSelectorException(self.key, "Exception selecting output data") from e

        if verbose:
            vdata = b'\n\t'.join(self.output_data or selected_data).decode()
            print(f"{self.key}:\n\t{vdata}\n")
        else:
            key_digest = hashlib.sha256(self.key.encode()).hexdigest()
            data_digest = hashlib.sha256()
            for datum in selected_data:
                data_digest.update(datum)
            data_digest = data_digest.hexdigest()
            print(f"{key_digest}:{data_digest}")

        return check_in_cache(cache, self.key, selected_data)

    def alert_message(self):
        message = self.key
        if self.comment is not None:
            message += "\n> " + "\n> ".join(self.comment.strip().splitlines()) + "\n"
        if getattr(self, "output_data", None) is not None:
            message += "\n* " + b'\n* '.join(x.strip() for x in self.output_data).decode()
        return message

class UrlWatch(Watch):
    cache = {}
    keys = {
        "method" : "GET",
        "headers" : {},
        "data" : None, 
        "code" : 200
    }

    def fetch(self):
        # Allow caching of URLs
        r = UrlWatch.cache.get(self.url)
        if r is None:
            r = requests.request(
                self.method,
                self.url,
                headers=self.headers,
                data=self.data)
            UrlWatch.cache[self.url] = r
        if r.status_code != self.code:
            raise WatchFetchException(self.key, f"Status code {r.status_code} != {self.code}")
        return r.content

class CmdWatch(Watch):
    keys = {
        "shell" : "/bin/sh",
        "timeout" : 30,
        "return_code" : 0
    }

    def fetch(self):
        p = subprocess.run([self.shell], input=self.cmd.encode(), timeout=self.timeout, capture_output=True)
        if p.returncode != self.return_code:
            raise WatchFetchException(self.key, f"Return code {p.returncode} != {self.return_code}")
        return p.stdout

class GroupWatch(Watch):
    @classmethod
    def decode(cls, **kwargs):
        objs = kwargs["group"]
        del kwargs["group"]
        o = super().decode(**kwargs)
        setattr(o, "group", Watch.load(objs))
        return o

    def in_cache(self, cache, verbose=False):
        uncached_keys = []
        for x in self.group:
           if not x.in_cache(cache, verbose=verbose):
               uncached_keys.append(x.key)
        if len(uncached_keys):
            self.key = "\n".join(uncached_keys)
            return False
        return True

def process(config, cache, verbose=False):
    watches = Watch.load(config.get("watch", []))
    for watch in watches:
        try:
            if not watch.in_cache(cache, verbose=verbose):
                alert(watch.alert_message(), alert_hook=config.get("hook"))
        except WatchException as e:
            key = e.key
            if not verbose:
                key = hashlib.sha256(key.encode()).hexdigest()
            sys.stderr.write(f"Error processing {key}:\n\t{e.__class__.__name__}: {e}\n")
            print(e.with_traceback())
            continue

def replace_var(vars, var):
    if var in vars:
        return vars[var]
    return os.environ.get(var, var)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", "-c", type=str, default="cache.yaml")
    parser.add_argument("--input", "-i", type=str, default="watch.yaml")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    with open(args.input) as f:
        config_data = f.read()
    
    config = yaml.safe_load(config_data)
    config_data = re.sub(r'\$\{([^}]+)\}', lambda match: replace_var(config.get("variables", {}), match.group(1)), config_data)
    config = yaml.safe_load(config_data)

    
    cache = read_cache(args.cache)
    process(config, cache, verbose=args.verbose)
    write_cache(args.cache, cache)
