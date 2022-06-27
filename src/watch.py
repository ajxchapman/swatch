import hashlib
import requests
import subprocess

from src.loadable import Loadable
from src.modifier import Modifier, ModifierException
from src.diff import Diff

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

class WatchContext:
    def __init__(self):
        self.output = None
        self.outputs = []
        self.variables = {}

    def add_output(self, output):
        self.output = output
        self.outputs.append(output)

    def add_variable(self, key, value):
        self.variables[key] = value

    def expand_context(self, value):
        pass


class Watch(Loadable):
    keys = {
        "selectors" : (list, []),
        "comment" : (str, None),
    }

    def apply_modifiers(self, modifiers, data, **kwargs):
        for modifier_data in modifiers:
            try:
                modifier = Modifier.load(**modifier_data, **kwargs)
            except ModifierException as e:
                raise WatchSelectorException(self.key, f"Error parsing modifiers") from e

            data = modifier.run_all(data)
        return data

    def fetch(self, ctx, *args, **kwargs):
        raise WatchFetchException(self.key, "Not implemented")

    def in_cache(self, ctx, cache, verbose=False):
        try:
            selected_data = self.apply_modifiers(self.selectors, [self.fetch(ctx)], key=self.key, cache=cache)
            # self.output_data = self.apply_modifiers(self.output, selected_data, key=self.key, cache=cache) if len(self.output) else None
        except (WatchFetchException, WatchSelectorException) as e:
            raise e
        except Exception as e:
            raise WatchSelectorException(self.key, f"Exception selecting data: {e}") from e

        cached = check_in_cache(cache, self.key, selected_data)
        if verbose:
            vdata = b'\n\t'.join(self.output_data or selected_data).decode()
            print(f"{self.key}:{cached}\n\t{vdata}\n")
        else:
            key_digest = hashlib.sha256(self.key.encode()).hexdigest()
            data_digest = hashlib.sha256()
            for datum in selected_data:
                data_digest.update(datum)
            data_digest = data_digest.hexdigest()
            print(f"{key_digest}:{data_digest}:{cached}")

        return cached

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
        "displayUrl" : ""
    }

    def render(self):
        return self.displayUrl or self.url

    def fetch(self, ctx):
        # Allow caching of URLs
        r = UrlWatch.cache.get(self.url)
        if r is None:
            r = requests.request(
                self.method,
                self.url,
                headers=self.headers,
                data=self.data)
            UrlWatch.cache[self.url] = r
        if self.code is not None and r.status_code != self.code:
            raise WatchFetchException(self.key, f"Status code {r.status_code} != {self.code}")
        return r.content

class CmdWatch(Watch):
    keys = {
        "shell" : "/bin/sh",
        "timeout" : 30,
        "return_code" : 0
    }

    def fetch(self, ctx):
        p = subprocess.run([self.shell], input=self.cmd.encode(), timeout=self.timeout, capture_output=True)
        if p.returncode != self.return_code:
            raise WatchFetchException(self.key, f"Return code {p.returncode} != {self.return_code}")
        return p.stdout

class GroupWatch(Watch):
    OPERATOR_ALL = ("all", "and")
    OPERATOR_ANY = ("any", "or")
    OPERATOR_LAST = "last"

    keys = {
        "operator" : "or"
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.group = [Watch.load(**x) for x in self.group]

    def render(self):
        return "Group[" + ", ".join([x.render() for x in self.group]) + "]"

    def in_cache(self, ctx, cache, verbose=False):
        result = [(x.key, x.in_cache(ctx, cache, verbose=verbose)) for x in self.group]
        if self.operator in GroupWatch.OPERATOR_ALL:
            return all([x[1] for x in result])
        elif self.operator in GroupWatch.OPERATOR_ANY:
            return any([x[1] for x in result])
        elif self.operator == GroupWatch.OPERATOR_LAST:
            return result[-1][1]
        raise WatchFetchException(f"Unknown operator '{self.operator}'")

class ConditionalWatch(Watch):
    keys = {
        "then" : {}
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.conditional = Watch.load(**self.conditional)
        self.then = Watch.load(**self.then)

    def render(self):
        return "Conditional(" + self.conditional.render() + ") {" + self.then.render() + "}"

    def in_cache(self, ctx, cache, verbose=False):
        if not self.conditional.in_cache(ctx, cache, verbose=verbose):
            return self.then.in_cache(ctx, cache, verbose=verbose)
        return True