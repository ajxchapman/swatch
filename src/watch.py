import logging
import os
import requests
import signal
import subprocess
import time
import typing
from urllib.parse import urlparse

from src.action import Action
from src.context import Context
from src.loadable import Loadable, hash_args
from src.match import Match, MatchException
from src.selector import Selector, SelectorException
from src.template import template_render

logger = logging.getLogger(__name__)

class WatchException(Exception):
    pass

class WatchFetchException(WatchException):
    pass

def render_comment(comments: typing.List[str], indent: int=0) -> str:
    _indent = indent
    output = []
    for i, x in enumerate(comments):
        if isinstance(x, str):
            if i == 0:
                _indent += 1
            output.append(indent * "  " + ("\n" + indent * "  ").join(x.splitlines()))
        else:
            _output = render_comment(x, indent=_indent)
            if len(_output) > 0:
                output.append(_output)
    return "\n".join(output)

class Watch(Loadable):
    keys = {
        "comment" : (str, None),
        "before" : (dict, None),
        "after" : (dict, None),
        "action_data" : (dict, None),
        "actions" : (list, list),
        "version" : (str, "1") # For cache busting
    }
    hash_skip = ["comment"]

    def get_comment(self, ctx: Context) -> typing.List[str]:
        return [ctx.expand_context(self.comment)] if self.comment is not None else []

    def get_data(self, ctx: Context) -> typing.List[dict]:
        if self.action_data is None:
            return []
        
        # Add default keys to the returned data
        return [{
            "id" : ctx.get_variable("hash"),
            "executed" : ctx.get_variable("cache").get_entry(f"{ctx.get_variable('hash')}-executed"), 
            **ctx.expand_context(self.action_data)
        }]

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        raise WatchException("Not implemented")

    def run(self, ctx: Context) -> None:
        """
        Entrypoint into the top level watch
        """
        starttime = time.time()
        config = ctx.get_variable("config")
        cache = ctx.get_variable("cache")
        
        actions = [Action.load(**x) for x in self.actions]
        if "default_actions" in config:
            try:
                actions.extend([Action.load(**x) for x in config["default_actions"]])
            except Exception as e:
                logger.warning("Unable to load default actions, skipping")

        try:
            trigger, comment, data = self.process(ctx)
        except:
            failure_count = (cache.get_entry(f"{self.hash}-failures") or 0) + 1
            cache.put_entry(f"{self.hash}-failures", failure_count)
            
            if ctx["config"].get("verbose") == True:
                logger.exception(f"{self.hash}:{int(time.time() - starttime):04}:Error:{failure_count}")
            else:
                logger.error(f"{self.hash}:{int(time.time() - starttime):04}:Error:{failure_count}")
            
            if failure_count in [3, 10, 25, 50]:
                action_data = {
                    "error": f"{self.hash}:{ctx.get_variable('watch_file')} has failed {failure_count} times in a row"
                }

                for action in actions:
                    action.error(ctx, action_data)
        else:
            if trigger:
                logger.info(f"{self.hash}:{int(time.time() - starttime):04}:True")

                action_data = {
                  "comment": render_comment(comment),
                  "data" : data
                }
                for action in actions:
                    action.report(ctx, action_data)
            else:
                logger.info(f"{self.hash}:{int(time.time() - starttime):04}:False")

# Watches which overload `fetch_data`

class DataWatch(Watch):
    keys = {
        "store" : (str, None),
        "selectors" : (list, list),
        "match" : (lambda x: x if isinstance(x, dict) else {"type" : x}, {"type" : "cache"}),
    }

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        """
        Return the raw data from the Watch
        """
        raise WatchFetchException("Not implemented")

    def select_data(self, ctx: Context, data: typing.List[bytes]) -> typing.List[bytes]:
        """
        Return the selected data from the Watch
        """
        for selector_kwargs in self.selectors:
            data = Selector.load(**selector_kwargs).run_all(ctx, data)
        return data

    def match_data(self, ctx: Context, data: typing.List[bytes]) -> bool:
        """
        Return a boolean indicating whether the processed data matches the configured match
        """
        if self.match is None:
            return True

        return Match.load(**self.match).match(ctx, data)

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        """
        Entrypoint into an individual (potentially nested) watch.
        Returns a tuple of (action_trigger, action_comment, action_data) with `action_trigger` True if the action_data of the Watch should be reported, False otherwise
        """
        cache = ctx.get_variable("cache")
        # Set the last run time
        cache.put_entry(f"{self.hash}-executed", int(time.time()))
        ctx.push_variable("hash", self.hash)

        try:
            # Execute the `before` step within the try block to ensure exception halt processing
            if self.before is not None:
                watch = Watch.load(**{**self.before, "match": "none"})
                watch.process(ctx)
                
            data = self.fetch_data(ctx)
            data = self.select_data(ctx, data)
            action_trigger = self.match_data(ctx, data)
        except:
            raise
        else:
            # Clear any previous failure count
            cache.put_entry(f"{self.hash}-failures", 0)

            if not action_trigger:
                return False, [], []

            # Store selected data in the context
            ctx.set_variable(self.hash, data)
            if self.store is not None:
                ctx.set_variable(self.store, data)
            ctx.push_variable("data", data)
            
            try:
                return True, self.get_comment(ctx), self.get_data(ctx)
            finally:
                ctx.pop_variable("data")
        finally:
             # Execute the `after` step within the finally block to ensure it is always executed
            if self.after is not None:
                watch = Watch.load(**{**self.after, "match": "none"})
                watch.process(ctx)
            ctx.pop_variable("hash")

class UrlWatch(DataWatch):
    keys = {
        "method" : (str, "GET"),
        "headers" : (dict, dict),
        "cookies" : (dict, dict),
        "data" : (str, None), 
        "code" : (lambda x: x if x is None else int(x), 200),
        "download" : (str, None)
    }

    def get_comment(self, ctx: Context) -> typing.List[str]:
        try:
            ctx.push_variable("URL", self.url)
            return super().get_comment(ctx)
        finally:
            ctx.pop_variable("URL")

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        ex_url = ctx.expand_context(self.url)
        ex_headers = ctx.expand_context(self.headers)
        ex_data = ctx.expand_context(self.data)
        ex_cookies = ctx.expand_context(self.cookies)
        
        # Use a per-context session for URL watches
        s = ctx.get_variable("requests_session")
        if s is None:
            s = requests.session()
            ctx.set_variable("requests_session", s)
        
        if len(ex_cookies) > 0:
            domain = urlparse(ex_url).hostname
            for k, v in ex_cookies.items():
                s.cookies.set(k, v, domain=domain)

        r = s.request(
            self.method,
            ex_url,
            headers=ex_headers,
            data=ex_data,
            stream=True if self.download is not None else False)
        
        logger.debug(f"UrlWatch: [{r.status_code} {r.reason}] {ex_url}")
        if self.code is not None and r.status_code != self.code:
            raise WatchFetchException(f"Status code {r.status_code} != {self.code}")
        
        if self.download is not None:
            location = os.path.abspath(os.path.join(os.getcwd(), self.download))
            if not location.startswith(os.getcwd() + "/"):
                raise WatchFetchException(f"Invalid download path '{self.download}'")
            with open(location, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return [location.encode()]
        
        return [r.content]

class CmdWatch(DataWatch):
    keys = {
        "shell" : (str, "/bin/sh"),
        "sudo": (bool, False),
        "timeout" : (lambda x: x if x is None else int(x), 30),
        "return_code" : (lambda x: x if x is None else int(x), 0),
        "output" : (lambda x: x if x in ["stdout", "stderr", "both"] else "stdout", "stdout")
    }

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        ex_cmd = ctx.expand_context(self.cmd)
        shell = [self.shell]
        if self.sudo:
            shell = ["sudo"] + shell

        logger.debug(f"CmdWatch: Executing command: {ex_cmd}")
        try:
            p = subprocess.Popen(shell, start_new_session=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate(ex_cmd.encode(), timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            if self.sudo:
                subprocess.run(["sudo", "/bin/kill", "--", f"-{os.getpgid(p.pid)}"])
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            raise WatchFetchException(f"CmdWatch: Command timeout after {self.timeout} seconds") from e

        logger.debug(f"CmdWatch: Return code: {p.returncode}")
        _stdout = "\n\t" + "\n\t".join(stdout.decode().splitlines()) if len(stdout) else ""
        _stderr = "\n\t" + "\n\t".join(stderr.decode().splitlines()) if len(stderr) else ""
        if self.return_code is not None and p.returncode != self.return_code:
            raise WatchFetchException(f"CmdWatch: Return code {p.returncode} != {self.return_code}\nStdout:{_stdout}\nStderr:{_stderr}")

        logger.debug(f"CmdWatch: Stdout: {_stdout}")
        logger.debug(f"CmdWatch: Stderr: {_stderr}")

        if self.output == "stderr":
            return [stderr]
        elif self.output == "both":
            return [stdout, stderr]
        return [stdout]


# Watches which overload `process`

class MultipleWatch(Watch):
    OPERATOR_ALL = ("all", "and")
    OPERATOR_ANY = ("any", "or")
    OPERATOR_LAST = "last"

    keys = {
        "operator" : "any"
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.watches = []


    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        comment = []
        data = []
        trigger = False
        _trigger = False

        for watch in self.watches:
            _trigger, _comment, _data = watch.process(ctx)
            if self.operator in GroupWatch.OPERATOR_ALL:
                if not _trigger:
                    # Early exit on the ALL operator
                    return False, [], []

            trigger |= _trigger
            if _trigger:
                comment.extend(_comment)
                data.extend(_data)

        if not trigger:
            return False, [], []

        if self.operator == GroupWatch.OPERATOR_LAST:
            comment = [comment[-1]] if len(comment) else []
            data = [data[-1]] if len(data) else []
            trigger = _trigger

        if self.comment is not None:
            comment = [*super().get_comment(ctx), comment]
        return trigger, comment, data

class GroupWatch(MultipleWatch):
    default_key = "group"
    keys = {
        "group" : (list, list)
    }

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        self.watches = [Watch.load(**x) for x in self.group]
        return super().process(ctx)

class LoopWatch(MultipleWatch):
    default_key = "loop"
    keys = {
        "loop" : (dict, dict),
        "do" : (dict, dict),
        "as" : (str, "loop"),
        "operator" : (str, "all"),
    }

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        loop = Watch.load(**{**self.loop, "version": self.version})
        trigger, _, _ = loop.process(ctx)
        if not trigger:
            return False, [], []
        
        # Create a new tempalte based off the `do` definition
        ctx.get_variable("templates")[self.hash] = self.do
        self.watches = []
        for data in ctx.get_variable(loop.hash):
            self.watches.append(Watch.load(template=self.hash, variables={getattr(self, "as"): data}))
        
        return super().process(ctx)
    
class SubWatch(Watch):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.subwatch = None

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        if not isinstance(self.subwatch, Watch):
            self.subwatch = Watch.load(**{**self.subwatch, "version": self.version})

        trigger, comment, data = self.subwatch.process(ctx)
        if trigger:
            if self.comment is not None:
                comment = [*self.get_comment(ctx), comment]

        return trigger, comment, data

class ConditionalWatch(SubWatch):
    keys = {
        "operator" : (str, "and"), 
        "then" : (dict, dict)       # `then` is a more appropiate name than `subwatch` for conditionals
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(self.conditional, list):
            self.conditional = [self.conditional]
        self.conditional = Watch.load(group=self.conditional, operator=self.operator, version=self.version)
        self.subwatch = Watch.load(**{**self.then, "version": self.version})

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        trigger, _, _ = self.conditional.process(ctx)
        if not trigger:
            return False, [], []
        
        return super().process(ctx)

class OnceWatch(SubWatch):
    keys = {
        "once" : (dict, dict)
    }

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        cache = ctx.get_variable("cache")
        if cache.get_entry(f"{self.hash}-once") is not None:
            return False, [], []

        self.subwatch = Watch.load(**self.once)
        trigger, comment, data = super().process(ctx)
        if trigger:
            cache.put_entry(f"{self.hash}-once", True)
        return trigger, comment, data

class TemplateWatch(SubWatch):
    keys = {
        "template" : (str, None),
        "variables" : (dict, dict),
    }

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        template = ctx.get_variable("templates").get(self.template)
        if template is None:
            raise WatchException(f"Unknown template '{self.template}'")
        
        # Load and fixup the template hash to ensure it is unique per variable set
        self.subwatch = Watch.load(**template)
        self.subwatch.update_hash(self.variables)

        # Push template variables into the context
        for k, v in self.variables.items():
            ctx.push_variable(k, v)

        try:
            return super().process(ctx)
        finally:
            # Pop template variables from the context
            for k in self.variables.keys():
                ctx.pop_variable(k)

