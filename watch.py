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

def process(config: dict, cache: Cache, watch_files: typing.List[str], template_file: typing.List[str]) -> None:
    cwd = os.getcwd()

    # Load global templates
    templates = {}
    for template_file in template_files:
        with open(template_file) as f:
            template_config = yaml.safe_load(f)
            templates.update(template_config.get("templates", {}))

    for watch_file in watch_files:
        with open(watch_file) as f:
            watch_config = yaml.safe_load(f)
        if watch_config is None:
            continue
        
        ctx = Context()
        ctx.set_variable("config", config)
        ctx.set_variable("cache", cache)
        ctx.set_variable("watch_file", watch_file)
        ctx.set_variable("base_dir", cwd)
        # Load templates into the context
        ctx.set_variable("templates", {**templates, **watch_config.get("templates", {})})
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
                        watch.execute(ctx)
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

    template_files = set()
    watch_files = set()
    if config.get("templates") is not None:
        template_glob = os.path.join(os.path.dirname(args.config), config.get("templates"), "**/*.y*ml")
        template_files = set(glob.glob(template_glob, recursive=True))
    for x in args.watches:
        if os.path.isfile(x):
            watch_files.add(x)
        else:
            watch_files.update(glob.glob(os.path.join(x, "**/*.y*ml"), recursive=True))
    
    watch_files -= template_files
    logger.debug(f"Loading watch files: {watch_files}")
    logger.debug(f"Loading template files: {template_files}")

    if args.find:
        find(watch_files, args.find)
    elif args.test:
        process(config, Cache(cache_path=None), watch_files, template_files)
    else:
        cache = Cache(cache_path=args.cache, encryption_key=config.get("key"))
        try:
            process(config, cache, watch_files, template_files)
        finally:
            cache.close()
