import argparse
import glob
import hashlib
import json
import os
import re
import tempfile
import traceback
import requests
import sys
import yaml

from src.watch import *

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

def process(config, cache, verbose=False):
    watches = [Watch.load(**x) for x in config.get("watch", [])]
    cwd = os.getcwd()

    for watch in watches:
        # Create a new context and temporary working directory for each watch
        ctx = WatchContext()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            ctx.add_variable("tmpdir", tmpdir)
            try:
                if not watch.in_cache(ctx, cache, verbose=verbose):
                    alert(watch.alert_message(), alert_hook=config.get("hook"))
            except WatchException as e:
                key = e.key
                if not verbose:
                    key = hashlib.sha256(key.encode()).hexdigest()
                sys.stderr.write(f"Error processing {key}:\n\t{e.__class__.__name__}: {e}\n")
                traceback.print_tb(e.__traceback__)
                continue
            finally:
                os.chdir(cwd)

def replace_var(vars, var):
    if var in vars:
        return vars[var]
    return os.environ.get(var, var)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", "-c", type=str, default="cache.yaml")
    parser.add_argument("--input", "-i", type=str, default="watch.yaml")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--test", "-t", action="store_true")
    args = parser.parse_args()

    config = {}
    for watch_file in glob.glob(args.input, recursive=True):
        with open(watch_file) as f:
            watch_data = f.read()
    
        watch_config = yaml.safe_load(watch_data)
        watch_data = re.sub(r'\$\{([^}]+)\}', lambda match: replace_var(config.get("variables", {}), match.group(1)), watch_config)
        watch_config = yaml.safe_load(watch_data)
        config.setdefault("watch", []).append(watch_config["watch"])

    if args.test:
        process(config, {"watches" : {}}, verbose=args.verbose)
    else:
        cache = read_cache(args.cache)
        process(config, cache, verbose=args.verbose)
        write_cache(args.cache, cache)
