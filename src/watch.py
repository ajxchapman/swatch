import json
import os
import requests
import signal
import subprocess
import typing
from urllib.parse import urlparse


from src.context import Context
from src.diff import Diff
from src.loadable import Loadable, hash_args
from src.match import Match, MatchException
from src.selector import Selector, SelectorException
from src.template import template_render

class WatchException(Exception):
    def __init__(self, key, *args, **kwargs):
        self.key = key
        super().__init__(*args, **kwargs)

class WatchFetchException(WatchException):
    pass

class WatchSelectorException(WatchException):
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
        "selectors" : (list, []),
        "store" : (str, None),
        "match" : (lambda x: x if isinstance(x, dict) else {"type" : x}, {"type" : "cache"}),
        "diff" : (lambda x: x if isinstance(x, dict) else {"type" : x}, None),
        "comment" : (str, None),
        "before" : (dict, None),
        "after" : (dict, None),
        "version" : (str, "1") # For cache busting
    }
    hash_skip = ["comment"]

    def render(self) -> str:
        return self.hash

    def get_comment(self, ctx: Context) -> typing.List[str]:
        if self.comment is not None:
            data = ctx.get_variable(self.hash)
            if self.diff is not None:
                diff = Diff.load(**self.diff)
                data, cache_data = diff.diff(ctx.get_variable("cache").get_file(self.hash), data)
                ctx.get_variable("cache").put_file(self.hash, cache_data)
            
            return [template_render(self.comment, ctx.variables, data=data)]
        return []

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        """
        Return the raw data from the Watch
        """
        raise WatchFetchException(ctx.get_variable("hash"), "Not implemented")

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

    def process(self, ctx: Context) -> bool:
        ctx.set_variable("hash", self.hash)
        try:
            # Execute the `before` step if it exists
            if self.before is not None:
                watch = Watch.load(**{**self.before, "match": "none"})
                watch.process(ctx)
                
            data = self.fetch_data(ctx)
            data = self.select_data(ctx, data)
        except (WatchFetchException, WatchSelectorException) as e:
            raise e
        except Exception as e:
            raise e
            raise WatchSelectorException(self.hash, f"Exception processing watch: {e}") from e
        finally:
             # Execute the `after` step if it exists
            if self.after is not None:
                watch = Watch.load(**{**self.after, "match": "none"})
                watch.process(ctx)

        if self.store is not None:
            ctx.set_variable(self.store, data)
        # Store selected data in the context
        ctx.set_variable(self.hash, data)

        return self.match_data(ctx, data)

class UrlWatch(Watch):
    keys = {
        "method" : (str, "GET"),
        "headers" : (dict, dict),
        "cookies" : (dict, dict),
        "data" : (str, None), 
        "code" : (int, None),
        "download" : (str, None)
    }

    def render(self) -> str:
        return self.url

    def get_comment(self, ctx: Context) -> typing.List[str]:
        ctx.set_variable("URL", self.url)
        return super().get_comment(ctx)

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
        
        if self.code is not None and r.status_code != self.code:
            raise WatchFetchException(self.hash, f"Status code {r.status_code} != {self.code}")
        
        if self.download is not None:
            location = os.path.abspath(os.path.join(os.getcwd(), self.download))
            if not location.startswith(os.getcwd() + "/"):
                raise WatchFetchException(f"Invalid download path '{self.download}'")
            with open(location, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return [location.encode()]
        
        return [r.content]

class CmdWatch(Watch):
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

        try:
            p = subprocess.Popen(shell, start_new_session=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = p.communicate(ex_cmd.encode(), timeout=self.timeout)
        except subprocess.TimeoutExpired:
            if self.sudo:
                subprocess.run(["sudo", "/bin/kill", "--", f"-{os.getpgid(p.pid)}"])
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            raise WatchFetchException(self.hash, "Command Timeout")

        if self.return_code is not None and p.returncode != self.return_code:
            raise WatchFetchException(self.hash, f"Return code {p.returncode} != {self.return_code}")

        if self.output == "stderr":
            return [stderr]
        elif self.output == "both":
            return [stdout, stderr]
        return [stdout]

class MultipleWatch(Watch):
    OPERATOR_ALL = ("all", "and")
    OPERATOR_ANY = ("any", "or")
    OPERATOR_LAST = "last"

    keys = {
        "selectors": (None, list), # Selectors do not make sense here
        "match": (None, None), # Match does not make sense here
        "operator" : "any",
        "matched" : (None, list),
        "comments" : (None, list)
    }

    def get_comment(self, ctx: Context) -> typing.List[str]:
        if self.comment is None:
            return self.comments
        return [template_render(self.comment, ctx.variables), *self.comments]

    def match_data(self, ctx: Context, data: typing.List[bytes]) -> bool:
        # Return False if no elements were fetched
        if len(self.matched) == 0:
            return False
        
        if self.operator in GroupWatch.OPERATOR_ALL:
            return all(self.matched)
        elif self.operator in GroupWatch.OPERATOR_ANY:
            return any(self.matched)
        elif self.operator == GroupWatch.OPERATOR_LAST:
            return self.matched[-1]
        raise WatchFetchException(f"Unknown operator '{self.operator}'")

class GroupWatch(MultipleWatch):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure to propogate 'version' up the tree
        self.group = [Watch.load(**{**x, "version" : self.version}) for x in self.group]

    def render(self) -> str:
        return "Group[" + ", ".join([x.render() for x in self.group]) + "]"

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        data = []
        for x in self.group:
            match = x.process(ctx)
            self.matched.append(match)
            if match:
                data.extend(ctx.get_variable(x.hash))
                # Early evaluate comments to mitigate context changes
                self.comments.append(x.get_comment(ctx))
            # Early exit of 'all' operator
            if self.operator in GroupWatch.OPERATOR_ALL and not match:
                break
        return data

class LoopWatch(MultipleWatch):
    keys = {
        "do" : (dict, {}),
        "as" : (str, "data")
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.loop = Watch.load(**{**self.loop, "version": self.version})
        self.iterations = []

    def render(self) -> str:
        return "Loop(" + self.loop.render() + ") {" + self.do.render() + "}"
    
    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        data = []
        if self.loop.process(ctx):
            for datum in ctx.get_variable(self.loop.hash):
                # Dynamically create a new Watch object for each loop iteration
                w = Watch.load(**{**self.do, "version": self.version})
                self.iterations.append(w)

                # Need to update the dynamically created object hash for each loop iteration
                w.hashobj = hash_args(datum, w.hashobj)
                w.hash = w.hashobj.hexdigest()

                ctx.set_variable(getattr(self, "as"), datum)
                match = w.process(ctx)
                self.matched.append(match)
                if match:
                    data.extend(ctx.get_variable(w.hash))
                     # Early evaluate comments to mitigate context changes
                    self.comments.append(w.get_comment(ctx))
                # Early exit of 'all' operator
                if self.operator in GroupWatch.OPERATOR_ALL and not match:
                    break
        return data

class ConditionalWatch(Watch):
    keys = {
        "selectors": (None, list), # Selectors do not make sense for 'conditional'
        "match": (None, None), # Match does not make sense for 'conditional'
        "operator" : (str, "and"), 
        "then" : (dict, dict)
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(self.conditional, list):
            self.conditional = [self.conditional]
        self.conditional = Watch.load(group=self.conditional, operator=self.operator, version=self.version)
        self.then = Watch.load(**{**self.then, "version": self.version})
        self.matched = False

    def render(self) -> str:
        return "Conditional(" + self.conditional.render() + ") {" + self.then.render() + "}"

    def get_comment(self, ctx: Context) -> typing.List[str]:
        if self.comment is None:
            return self.then.get_comment(ctx)
        return [template_render(self.comment, ctx.variables), self.then.get_comment(ctx)]

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        if self.conditional.process(ctx):
            self.matched = self.then.process(ctx)
            return ctx.get_variable(self.then.hash)
        return []
    
    def match_data(self, ctx: Context, data: typing.List[bytes]) -> bool:
        return self.matched