import argparse
import hashlib
import json
import os
import re
import requests
import subprocess
import sys
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
    data_digest = hashlib.sha256(data).hexdigest()

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

class WatchException(Exception):
    def __init__(self, key, *args, **kwargs):
        self.key = key
        super().__init__(*args, **kwargs)

class WatchFetchException(WatchException):
    pass

class WatchSelectorException(WatchException):
    pass


class Watch:
    keys = {
        "selectors" : [],
        "comment" : ""
    }

    @classmethod
    def load(cls, object_definitions):
        # Load default key values from the Watch subclasses
        decoders = {}
        class_keys = {}
        for c in cls.__subclasses__():
            decoders[c.__name__.replace(cls.__name__, "").lower()] = c
        for c in cls.__subclasses__():
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

    def apply_selectors(self, data):
        for selector in self.selectors:
            skey = next(selector.keys().__iter__())
            pattern = selector[skey]
            if skey == "regex":
                m = re.search(pattern.encode(), data, re.MULTILINE)
                data = m.group() if m else b''
            elif skey == "jq":
                j = json.loads(data)
                data = jq.compile(pattern).input(j).text().encode()
            elif skey == "css":
                soup = BeautifulSoup(data, "html.parser")
                data = json.dumps([str(x) for x in soup.select(pattern)]).encode()
            elif skey == "bytes":
                start, end = (pattern.split(":") + [""])[:2]
                data = data[int(start) if start.isdigit() else 0:int(end) if end.isdigit() else None]
            elif skey == "lines":
                start, end = (pattern.split(":") + [""])[:2]
                data = "".join(data.splitlines(keepends=True)[int(start) if start.isdigit() else 0:int(end) if end.isdigit() else None])
            else:
                raise WatchSelectorException(self.key, f"Unknown selector {stype}")
        return data

    def fetch(self, *args, **kwargs):
        raise WatchFetchException(self.key, "Not implemented")

    def in_cache(self, cache, verbose=False):
        data = self.apply_selectors(self.fetch())
        if verbose:
            vdata = "\n\t" + "\n\t".join(data.decode().splitlines())
            print(f"{self.key}:{vdata}\n")
        else:
            key_digest = hashlib.sha256(self.key.encode()).hexdigest()
            data_digest = hashlib.sha256(data).hexdigest()
            print(f"{key_digest}:{data_digest}")

        return check_in_cache(cache, self.key, data)

    def alert_message(self):
        message = self.key
        if self.comment is not None:
            message += f"\n> {self.comment.strip()}"
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
            continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", "-c", type=str, default="cache.yaml")
    parser.add_argument("--input", "-i", type=str, default="watch.yaml")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    with open(args.input) as f:
    
    cache = read_cache(args.cache)
    process(config, cache, verbose=args.verbose)
    write_cache(args.cache, cache)
