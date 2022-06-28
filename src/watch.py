import hashlib
import requests
import subprocess
import typing

from src.loadable import Loadable
from src.modifier import Modifier, ModifierException
from src.match import Match, MatchException
from src.context import WatchContext

def check_in_cache(cache, key, data):
    key_digest = hashlib.sha256(key.encode()).hexdigest()
    data_digest = hashlib.sha256()
    for datum in data:
        data_digest.update(datum)
    data_digest = data_digest.hexdigest()

    # If the key_digest is not previously watched, or the data_digest does not match the cache, alert
    if cache["watches"].get(key_digest) != data_digest:
        cache["watches"][key_digest] = data_digest
        return False
    return True

class WatchException(Exception):
    def __init__(self, key, *args, **kwargs):
        self.key = key
        super().__init__(*args, **kwargs)

class WatchFetchException(WatchException):
    pass

class WatchSelectorException(WatchException):
    pass


class Watch(Loadable):
    keys = {
        "selectors" : (list, []),
        "match" : (dict, {"type" : "cache"}),
        "comment" : (str, None),
    }

    def apply_selectors(self, ctx: WatchContext, data: typing.List[bytes]) -> typing.List[bytes]:
        for selector_kwargs in self.selectors:
            try:
                modifier: Modifier = Modifier.load(**selector_kwargs)
            except ModifierException as e:
                raise WatchException(self.key, f"Error parsing modifier: {e}") from e

            data = modifier.run_all(ctx, data)
        return data

    def fetch_data(self, ctx: WatchContext, *args, **kwargs) -> typing.List[bytes]:
        """
        Return the raw data from the Watch
        """
        raise WatchFetchException(self.key, "Not implemented")

    def process_data(self, ctx: WatchContext) -> typing.List[bytes]:
        """
        Return the processed data from the Watch
        """
        try:
            ctx.set_variable("key", self.hash)
            data = self.fetch_data(ctx)
            selected_data = self.apply_selectors(ctx, [data])
        except (WatchFetchException, WatchSelectorException) as e:
            raise e
        except Exception as e:
            raise WatchSelectorException(self.key, f"Exception selecting data: {e}") from e

        return selected_data

    def match_data(self, ctx: WatchContext, data: typing.List[bytes]) -> bool:
        """
        Return a boolean indicating whether the processed data matches the configured match
        """
        try:
            match = Match.load(**self.match)
        except MatchException as e:
            raise WatchException(self.key, f"Error parsing match: {e}") from e
        return match.match(ctx, data)

    def render(self):
        return self.key

    def alert_message(self):
        message = self.render()

        if self.comment is not None:
            message += "\n> " + "\n> ".join(self.comment.strip().splitlines()) + "\n"
        if getattr(self, "output_data", None) is not None:
            message += "\n* " + b'\n* '.join(x.strip() for x in self.output_data).decode()
        return message

class UrlWatch(Watch):
    cache = {}
    keys = {
        "method" : "GET",
        "headers" : {},
        "data" : None, 
        "code" : None,
    }

    def render(self):
        return self.url

    def fetch_data(self, ctx: WatchContext):
        r = requests.request(
            self.method,
            self.url,
            headers=self.headers,
            data=self.data)
        if self.code is not None and r.status_code != self.code:
            raise WatchFetchException(self.key, f"Status code {r.status_code} != {self.code}")
        return r.content

class CmdWatch(Watch):
    keys = {
        "shell" : "/bin/sh",
        "timeout" : 30,
        "return_code" : 0
    }

    def fetch_data(self, ctx):
        p = subprocess.run([self.shell], input=self.cmd.encode(), timeout=self.timeout, capture_output=True)
        if self.return_code is not None and p.returncode != self.return_code:
            raise WatchFetchException(self.key, f"Return code {p.returncode} != {self.return_code}")
        return p.stdout

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

    def render(self):
        return "Group[" + ", ".join([x.render() for x in self.group]) + "]"

    def process_data(self, ctx: WatchContext, verbose: bool = False) -> typing.List[bytes]:
        return []

    def match_data(self, ctx: WatchContext, data: typing.List[bytes]) -> bool:
        match = False
        for x in self.group:
            xmatch = x.match_data(ctx, x.process_data(ctx))
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
        "then" : {}
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.conditional = Watch.load(**self.conditional)
        self.then = Watch.load(**self.then)

    def render(self):
        return "Conditional(" + self.conditional.render() + ") {" + self.then.render() + "}"

    def process_data(self, ctx: WatchContext, verbose: bool = False) -> typing.List[bytes]:
        return []

    def match_data(self, ctx: WatchContext, data: typing.List[bytes]) -> bool:
        match = self.conditional.match_data(ctx, self.conditional.process_data(ctx))
        if match:
            return self.then.match_data(ctx, self.then.process_data(ctx))
        return False