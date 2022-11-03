import argparse
import glob
import json
import os
import tempfile
import traceback
import requests
import time
import typing
import yaml

from src.cache import Cache
from src.context import Context
from src.watch import Watch, WatchException, render_comment


def alert(message:str, alert_hook: str=None) -> None:
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

def find(watch_files, hash):
    for watch_file in watch_files:
        with open(watch_file) as f:
            watch_config = yaml.safe_load(f)
        for watch in watch_config.get("watch", []):
            _watch = Watch.load(**watch)
            print(_watch.hash, watch_file)
            if _watch.hash == hash:
                print(watch_file, json.dumps(watch))
                return

def process(config: dict, cache: Cache, watch_files: typing.List[str], verbose: bool=False):
    cwd = os.getcwd()
    for watch_file in watch_files:
        with open(watch_file) as f:
            watch_config = yaml.safe_load(f)
        
        ctx = Context()
        ctx.set_variable("cache", cache)
         # Load variables into the context
        for k, v in watch_config.get("variables", {}).items():
            ctx.set_variable(k, ctx.expand_context(v))
        # Load templates into the context
        ctx.set_variable("templates", watch_config.get("templates", {}))

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
                        starttime = time.time()
                        if watch.process(ctx):
                            print(f"{watch.hash}:{int(time.time() - starttime):04}:True")
                            alert(render_comment(watch.get_comment(ctx)), config.get("hook"))
                        else:
                            print(f"{watch.hash}:{int(time.time() - starttime):04}:False")
                    except:
                        failure_count = cache.get_entry(f"{watch.hash}-failures")
                        print(f"{watch.hash}:{int(time.time() - starttime):04}:Error:{failure_count}")
                        if verbose:
                            traceback.print_exc()
                        if failure_count in [3, 10, 25, 50]:
                            alert(f"{watch.hash}:{watch_file} has failed {failure_count} times in a row")

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
    parser.add_argument("--find", type=str, default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--test", "-t", action="store_true")
    parser.add_argument('watches', type=str, nargs=argparse.REMAINDER)
    args = parser.parse_args()

    config = {}
    if not (args.test):
        if os.path.isfile(args.config):
            with open(args.config) as f:
                config = yaml.safe_load(f).get("config", {})

    watch_files = set([x for xs in [[y] if os.path.isfile(y) else glob.glob(os.path.join(y, "**/*.y*ml"), recursive=True) for y in args.watches] for x in xs])

    if args.find:
        find(watch_files, args.find)
    elif args.test:
        process(config, Cache(cache_path=None), watch_files, verbose=args.verbose)
    else:
        cache = Cache(cache_path=args.cache, encryption_key=config.get("key"))
        try:
            process(config, cache, watch_files, verbose=args.verbose)
        finally:
            cache.close()
