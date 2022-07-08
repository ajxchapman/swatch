import argparse
import glob
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
        ctx = Context()
        ctx.set_variable("cache", cache)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)
                ctx.set_variable("tmpdir", tmpdir)
                try:
                    if watch.match_data(ctx, watch.process_data(ctx)):
                        print(f"{watch.hash}:True")
                        alert(render_comment(watch.get_comment(ctx)), config["config"].get("hook"))
                    else:
                        print(f"{watch.hash}:False")
                except WatchException as e:
                    key = e.key
                    print(f"Error processing {key}:\n\t{e.__class__.__name__}: {e}")
                    traceback.print_tb(e.__traceback__, file=sys.stdout)
                finally:
                    os.chdir(cwd)
        except PermissionError:
            print(f"Error removing temporary directory\n")

def replace_var(vars, var):
    if var in vars:
        return vars[var]
    return os.environ.get(var, var)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", "-c", type=str, default="cache.yaml")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--test", "-t", action="store_true")
    parser.add_argument('watches', nargs=argparse.REMAINDER)
    args = parser.parse_args()

    config = {
        "watch": [],
        "config": {}
    }
    for watch_file in set([x for xs in [glob.glob(y, recursive=True) for y in args.watches] for x in xs]):
        with open(watch_file) as f:
            watch_data = f.read()
    
        watch_config = yaml.safe_load(watch_data)
        watch_data = re.sub(r'\$\{([^}]+)\}', lambda match: replace_var(watch_config.get("variables", {}), match.group(1)), watch_data)
        watch_config = yaml.safe_load(watch_data)
        config["watch"].extend(watch_config.get("watch", []))

        if len(config["config"].keys() & watch_config.get("config", {}).keys()) > 0:
            raise Exception(f"Conflicting config keys {list(config['config'].keys() & watch_config['config'].keys())} in '{watch_file}'")
        config["config"].update(watch_config.get("config", {}))

    if args.test:
        process(config, Cache(cache_path=None), verbose=args.verbose)
    else:
        cache = Cache(cache_path=args.cache, encryption_key=config["config"].get("key"))
        try:
            process(config, cache, verbose=args.verbose)
        finally:
            cache.close()
