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

class FetchException(Exception):
    pass

class SelectorException(Exception):
    pass

class ProcessException(Exception):
    pass

def read_cache(filename):
    cache = {}
    if os.path.isfile(filename):
        with open(filename) as f:
            cache = yaml.safe_load(f)
    if not isinstance(cache, dict):
        cache = {}
    cache.setdefault("watches", {})
    return cache

def write_cache(obj, filename):
    with open(filename, "w") as f:
        yaml.dump(obj, f, default_flow_style=False)

def alert(watch, key, entry):
    hook = entry.get("hook", watch.get("hook", {}))

    message = f"{key} changed."
    if "comment" in entry:
        message += f"\n> {entry['comment']}"
    data = hook.get("payload", json.dumps({"text" : message})).replace("MESSAGE", json.dumps(message))

    if "url" in hook:
        r = requests.request(
            hook.get("method", "POST"),
            hook["url"],
            headers={"content-type" : hook.get("content-type", "application/json")},
            data=data.encode()
        )
    else:
        print(data)

def apply_selector(data, selectors):
    if selectors is None:
        return data
    if not isinstance(selectors, list):
        selectors = [selectors]

    for selector in selectors:
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
            raise SelectorException(f"Unknown selector {stype}")
    return data

def fetch_url(kurl, method="GET", headers={}, code=200, data=None, selector=None, **kwargs):
    r = requests.request(
        method,
        kurl,
        headers=headers,
        data=data)
    if r.status_code != code:
        raise FetchException(f"Status code {r.status_code} != {code}")
    return apply_selector(r.content, selector)

def fetch_cmd(kcmd, shell="/bin/sh", timeout=10, selector=None, return_code=0, **kwargs):
    p = subprocess.run([shell], input=kcmd.encode(), timeout=timeout, capture_output=True)
    if p.returncode != return_code:
        raise FetchException(f"Return code {p.returncode} != {return_code}")
    return apply_selector(p.stdout, selector)

def print_verbose(key, data):
    vdata = "\n\t" + "\n\t".join(data.decode().splitlines())
    print(f"{key}:{vdata}\n")

def check_cache(key, data, entry, cache):
    key_digest = hashlib.sha256(key.encode()).hexdigest()
    data_digest = hashlib.sha256(data).hexdigest()

    # If the key_digest is not previously watched, or the data_digest does not match the cache, alert
    if cache["watches"].get(key_digest) != data_digest:
        cache["watches"][key_digest] = data_digest
        alert(watch, key, entry)

def process(watch, cache, verbose=False):
    for entry in watch.get("watch", []):
        key = None
        try:
            if "url" in entry:
                key = entry["url"]
                data = fetch_url(key, **entry)
                if verbose:
                    print_verbose(key, data)
                check_cache(key, data, entry, cache)
            elif "urls" in entry:
                for key in entry["urls"]:
                    # Allow each URL entry to be either a string URL, or a sub-URL entry
                    _entry = {}
                    if isinstance(key, dict):
                        _entry = key
                        key = _entry["url"]
                    data = fetch_url(key, **{**entry, **_entry})
                    if verbose:
                        print_verbose(key, data)
                    check_cache(key, data, entry, cache)
            elif "cmd" in entry:
                key = entry["cmd"]
                data = fetch_cmd(key, **entry)
                if verbose:
                    print_verbose(key, data)
                check_cache(key, data, entry, cache)
            else:
                raise ProcessException("Unknown entry")
        except Exception as e:
            if key is None:
                sys.stderr.write(f"Unexpected error:\n\t{e.__class__.__name__}: {e}\n")
            else:
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

    cache = read_cache(args.cache)

    with open(args.input) as f:
        watch = yaml.safe_load(f)
    process(watch, cache, verbose=args.verbose)
    write_cache(cache, args.cache)
