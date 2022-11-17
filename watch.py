import argparse
import glob
import json
import logging
import os
import tempfile
import typing
import yaml

from src.cache import Cache
from src.context import Context
from src.watch import Watch, WatchException

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

def process(config: dict, cache: Cache, watch_files: typing.List[str]):
    cwd = os.getcwd()
    for watch_file in watch_files:
        with open(watch_file) as f:
            watch_config = yaml.safe_load(f)
        
        ctx = Context()
        ctx.set_variable("config", config)
        ctx.set_variable("cache", cache)
        ctx.set_variable("watch_file", watch_file)
        # Load templates into the context
        ctx.set_variable("templates", watch_config.get("templates", {}))
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
                        watch.run(ctx)
                    except WatchException:
                        # Early exit out of a watch_file in the event on an exception
                        break
                
                # Load an execute any 'after' tasks
                for after in [Watch.load(**x) for x in watch_config.get("after", [])]:
                    after.process(ctx)
        except PermissionError:
            print(f"Error removing temporary directory\n")
        finally:
            os.chdir(cwd)

if __name__ == "__main__":
    ch = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)8s %(name)s | %(message)s")
    ch.setFormatter(formatter)

    logger = logging.getLogger()
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", "-c", type=str, default="cache.tar.gz")
    parser.add_argument("--config", type=str, default="watches/conf.yml")
    parser.add_argument("--find", type=str, default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--test", "-t", action="store_true")
    parser.add_argument('watches', type=str, nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    config = {
        "default_actions" : [{"type" : "log"}],
        "verbose" : args.verbose or args.debug
    }
    if not (args.test):
        if os.path.isfile(args.config):
            with open(args.config) as f:
                config = {**config, **yaml.safe_load(f).get("config", {})}

    watch_files = set([x for xs in [[y] if os.path.isfile(y) else glob.glob(os.path.join(y, "**/*.y*ml"), recursive=True) for y in args.watches] for x in xs])
    logger.debug(f"Loading watch files: {watch_files}")

    if args.find:
        find(watch_files, args.find)
    elif args.test:
        process(config, Cache(cache_path=None), watch_files)
    else:
        cache = Cache(cache_path=args.cache, encryption_key=config.get("key"))
        try:
            process(config, cache, watch_files)
        finally:
            cache.close()
