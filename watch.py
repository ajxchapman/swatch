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

from src.cache import Cache
from src.context import Context
from src.watch import Watch, WatchException, render_comment


# def alert(message, alert_hook=None):
#     if alert_hook is not None:
#         data = alert_hook.get("payload", json.dumps({"text" : message})).replace("MESSAGE", json.dumps(message))
#         r = requests.request(
#             alert_hook.get("method", "POST"),
#             alert_hook["url"],
#             headers={"content-type" : alert_hook.get("content-type", "application/json")},
#             data=data.encode()
#         )
#     else:
#         print(message)

def process(config, cache, verbose=False):
    watches = [Watch.load(**x) for x in config.get("watch", [])]
    cwd = os.getcwd()

    for watch in watches:
        # Create a new context and temporary working directory for each watch
        ctx = Context()
        ctx.set_variable("cache", cache)
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            ctx.set_variable("tmpdir", tmpdir)
            try:
                if watch.match_data(ctx, watch.process_data(ctx)):
                    print(render_comment(watch.get_comment(ctx)))
            except WatchException as e:
                key = e.key
                if not verbose:
                    key = hashlib.sha256(key.encode()).hexdigest()
                sys.stderr.write(f"Error processing {key}:\n\t{e.__class__.__name__}: {e}\n")
                traceback.print_tb(e.__traceback__)
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
        watch_data = re.sub(r'\$\{([^}]+)\}', lambda match: replace_var(watch_config.get("variables", {}), match.group(1)), watch_data)
        watch_config = yaml.safe_load(watch_data)
        config.setdefault("watch", []).extend(watch_config["watch"])

    if args.test:
        process(config, Cache(cache_path=None), verbose=args.verbose)
    else:
        cache = Cache(cache_path=args.cache)
        try:
            process(config, cache, verbose=args.verbose)
        finally:
            cache.close()
