import json
import os
import requests
import subprocess
import typing

from src.context import Context
from src.diff import Diff
from src.loadable import Loadable
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
            output.append(indent * "\t" + x)
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
        "version" : (str, "1") # For cache busting
    }

    def apply_selectors(self, ctx: Context, data: typing.List[bytes]) -> typing.List[bytes]:
        for selector_kwargs in self.selectors:
            try:
                modifier: Selector = Selector.load(**selector_kwargs)
            except SelectorException as e:
                raise WatchException(self.hash, f"Error parsing modifier: {e}") from e

            data = modifier.run_all(data)
        return data

    def fetch_data(self, ctx: Context, *args, **kwargs) -> typing.List[bytes]:
        """
        Return the raw data from the Watch
        """
        raise WatchFetchException(ctx.get_variable("key"), "Not implemented")

    def process_data(self, ctx: Context) -> typing.List[bytes]:
        """
        Return the processed data from the Watch
        """
        try:
            ctx.set_variable("key", self.hash)
            data = self.fetch_data(ctx)
            selected_data = self.apply_selectors(ctx, data)
        except (WatchFetchException, WatchSelectorException) as e:
            raise e
        except Exception as e:
            raise WatchSelectorException(ctx.get_variable("key"), f"Exception selecting data: {e}") from e

        if self.store is not None:
            ctx.set_variable(self.store, selected_data)
        ctx.set_variable(self.hash, selected_data)

        return selected_data

    def match_data(self, ctx: Context, data: typing.List[bytes]) -> bool:
        """
        Return a boolean indicating whether the processed data matches the configured match
        """
        try:
            match = Match.load(**self.match)
        except MatchException as e:
            raise WatchException(self.hash, f"Error parsing match: {e}") from e
        return match.match(ctx, data)

    def render(self):
        return self.hash

    def get_comment(self, ctx: Context):
        if self.comment is not None:
            data = ctx.get_variable(self.hash)
            if self.diff is not None:
                diff = Diff.load(**self.diff)
                old_data = ctx.get_variable("cache").get_file(self.hash)
                ctx.get_variable("cache").put_file(self.hash, data)
                data = diff.diff(old_data, data)
            
            return [template_render(self.comment, ctx.variables, data=data)]
        return []

class UrlWatch(Watch):
    keys = {
        "method" : "GET",
        "headers" : {},
        "data" : None, 
        "code" : None,
        "download" : (str, None),
    }

    def render(self):
        return self.url

    def get_comment(self, ctx: Context):
        ctx.set_variable("URL", self.url)
        return super().get_comment(ctx)

    def fetch_data(self, ctx: Context) -> bytes:
        ex_url = ctx.expand_context(self.url)
        ex_headers = ctx.expand_context(self.headers)
        
        r = requests.request(
            self.method,
            ex_url,
            headers=ex_headers,
            data=self.data,
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
        "timeout" : (int, 30),
        "return_code" : (int, 0)
    }

    def fetch_data(self, ctx: Context) -> bytes:
        ex_cmd = ctx.expand_context(self.cmd)
        shell = [self.shell]
        if self.sudo:
            shell = ["sudo"] + shell
        p = subprocess.run(shell, input=ex_cmd.encode(), timeout=self.timeout, capture_output=True)
        if self.return_code is not None and p.returncode != self.return_code:
            raise WatchFetchException(self.hash, f"Return code {p.returncode} != {self.return_code}")
        return [p.stdout]

class GroupWatch(Watch):
    OPERATOR_ALL = ("all", "and")
    OPERATOR_ANY = ("any", "or")
    OPERATOR_LAST = "last"

    keys = {
        "selectors": (None, []), # Selectors do not make sense for 'group'
        "match": (None, None), # Match does not make sense for 'group'
        "operator" : "or"
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.group = [Watch.load(**x) for x in self.group]
        self.matched = []

    def render(self):
        return "Group[" + ", ".join([x.render() for x in self.group]) + "]"

    def process_data(self, ctx: Context, verbose: bool = False) -> typing.List[bytes]:
        return []

    def get_comment(self, ctx: Context):
        subcomments = [x.get_comment(ctx) for x in self.matched]
        if self.comment is None:
            return subcomments
        return [self.comment, *subcomments]

    def match_data(self, ctx: Context, data: typing.List[bytes]) -> bool:
        match = False
        for x in self.group:
            xmatch = x.match_data(ctx, x.process_data(ctx))
            if xmatch:
                self.matched.append(x)
            # Early exit of and operator
            if self.operator in GroupWatch.OPERATOR_ALL and not xmatch:
                return False
            match |= xmatch

        if self.operator in GroupWatch.OPERATOR_ALL:
            return True
        elif self.operator in GroupWatch.OPERATOR_ANY:
            return match
        elif self.operator == GroupWatch.OPERATOR_LAST:
            return xmatch
        raise WatchFetchException(f"Unknown operator '{self.operator}'")

class ConditionalWatch(Watch):
    keys = {
        "selectors": (None, []), # Selectors do not make sense for 'conditional'
        "match": (None, None), # Match does not make sense for 'conditional'
        "operator" : (str, "and"), 
        "then" : (dict, {})
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(self.conditional, list):
            self.conditional = [self.conditional]
        self.conditional = Watch.load(group=self.conditional, operator=self.operator)
        self.then = Watch.load(**self.then)
        self.matched = None

    def render(self):
        return "Conditional(" + self.conditional.render() + ") {" + self.then.render() + "}"

    def process_data(self, ctx: Context, verbose: bool = False) -> typing.List[bytes]:
        return []

    def get_comment(self, ctx: Context):
        if self.comment is None:
            return self.then.get_comment(ctx)
        return [self.comment, self.then.get_comment(ctx)]

    def match_data(self, ctx: Context, data: typing.List[bytes]) -> bool:
        self.matched = self.conditional.match_data(ctx, self.conditional.process_data(ctx))
        if self.matched:
            return self.then.match_data(ctx, self.then.process_data(ctx))
        return self.matched