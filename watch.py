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

def process(config, cache, watch_files, verbose=False):
    cwd = os.getcwd()
    for watch_file in watch_files:
        with open(watch_file) as f:
            watch_config = yaml.safe_load(f)
        
        ctx = Context()
        ctx.set_variable("cache", cache)
         # Load variables into the context
        for k, v in watch_config.get("variables", {}).items():
            ctx.set_variable(k, ctx.expand_context(v))

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)
                ctx.set_variable("tmpdir", tmpdir)

                # Load an execute any 'before' tasks
                for before in [Watch.load(**x) for x in watch_config.get("before", [])]:
                    before.process(ctx)
                
                # Execute main 'watch' tasks
                for watch in [Watch.load(**x) for x in watch_config.get("watch", [])]:
                    try:
                        if watch.process(ctx):
                            print(f"{watch.hash}:True")
                            alert(render_comment(watch.get_comment(ctx)), config.get("hook"))
                        else:
                            print(f"{watch.hash}:False")
                    except WatchException as e:
                        print(f"Error processing {e.hash}:\n\t{e.__class__.__name__}: {e}")
                        traceback.print_tb(e.__traceback__, file=sys.stdout)

                        # Early exit out of a watch_file in the event on an exception
                        break
                
                # Load an execute any 'after' tasks
                for after in [Watch.load(**x) for x in watch_config.get("after", [])]:
                    after.process(ctx)
        except PermissionError:
            print(f"Error removing temporary directory\n")
        finally:
            os.chdir(cwd)

def replace_var(vars, var):
    if var in vars:
        return vars[var]
    return os.environ.get(var, var)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", "-c", type=str, default="cache.tar.gz")
    parser.add_argument("--config", type=str, default="watches/conf.yml")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--test", "-t", action="store_true")
    parser.add_argument('watches', nargs=argparse.REMAINDER)
    args = parser.parse_args()

    config = {}
    if not (args.test):
        if os.path.isfile(args.config):
            with open(args.config) as f:
                config = yaml.safe_load(f).get("config", {})
    watch_files = set([x for xs in [glob.glob(y, recursive=True) for y in args.watches] for x in xs])

    if args.test:
        process(config, Cache(cache_path=None), watch_files, verbose=args.verbose)
    else:
        cache = Cache(cache_path=args.cache, encryption_key=config["config"].get("key"))
        try:
            process(config, cache, watch_files, verbose=args.verbose)
        finally:
            cache.close()
