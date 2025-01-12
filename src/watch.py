import logging
import os
import requests
import signal
import subprocess
import time
import typing
from urllib.parse import urlparse

from src.action import Action
from src.cache import Cache
from src.context import Context
from src.loadable import Loadable, LoadableException, type_one_of, type_none_or_type, type_list_of_type, type_choice
from src.match import Match
from src.selector import Selector, SelectorItem

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
        "before" : (type_list_of_type(dict), []),
        "after" : (type_list_of_type(dict), []),
        "action_data" : (dict, None),
        "actions" : (list, list),
    }
    hash_skip = ["comment"]
    type_determination_skip = ["before"]

    def get_comment(self, ctx: Context) -> typing.List[str]:
        return [ctx.expand_context(self.comment)] if self.comment is not None else []

    def get_data(self, ctx: Context) -> typing.List[dict]:
        if self.action_data is None:
            return []
        
        # Add default keys to the returned data
        return [{
            "id" : ctx.get_variable("hash"),
            "executed" : ctx.get_variable("starttime"), 
            **ctx.expand_context(self.action_data)
        }]

    def run(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        raise WatchException("Not implemented")
    
    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        """
        Entrypoint into an individual (potentially nested) watch.
        Returns a tuple of (action_trigger, action_comment, action_data) with `action_trigger` True if the action_data of the Watch should be reported, False otherwise
        """
        logger.debug(f"{self.__class__.__name__}: process enter")

        # Push a new frame into the context
        ctx.push_frame(self.hash)
        ctx.push_variable("hash", self.hash)

        try:
            # Execute the `before` step within the try block to ensure exception halt processing
            for watch in self.before:
                watch = Watch.load(**{**watch, "match": None})
                watch.process(ctx)
            
            trigger, comment, data = self.run(ctx)
        except:
            logger.debug(f"{self.__class__.__name__}: process exception")
            raise
        finally:
            # Execute the `after` step within the finally block to ensure it is always executed
            # Ignore exceptions thrown by the `after` block
            try:
               for watch in self.after:
                    watch = Watch.load(**{**watch, "match": None})
                    watch.process(ctx)
            except Exception as e:
                logger.debug(e, exc_info=1)
            
            # Pop the frame from the context clearing all context variables
            ctx.pop_frame(self.hash)
        
        logger.debug(f"{self.__class__.__name__}: process exit triggered {trigger}")
        if not trigger:
            return False, [], []
        return trigger, comment, data

    def execute(self, ctx: Context) -> None:
        """
        Entrypoint into the top level watch
        """
        starttime =  time.time()
        ctx.set_variable("starttime", int(starttime))
        config = ctx.get_variable("config")
        cache: Cache = ctx.get_variable("cache")
        
        actions = [Action.load(**x) for x in self.actions]
        if "default_actions" in config:
            try:
                actions.extend([Action.load(**x) for x in config["default_actions"]])
            except Exception as e:
                logger.warning("Unable to load default actions, skipping")

        try:
            # Cache the last run time
            cache.put_entry(f"{self.hash}-executed", ctx.get_variable("starttime"))
            trigger, comment, data = self.process(ctx)
        except:
            # Cache the failure count
            failure_count = cache.get_entry(f"{self.hash}-failures")
            cache.put_entry(f"{self.hash}-failures", failure_count + 1)
            
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
            # Clear cached failure count
            cache.put_entry(f"{self.hash}-failures", 0)

            if trigger:
                # Cache the last triggered time
                cache.put_entry(f"{self.hash}-triggered", ctx.get_variable("starttime"))
                logger.info(f"{self.hash}:{int(time.time() - starttime):04}:True")

                action_data = {
                  "comment": render_comment(comment),
                  "data" : data
                }

                for action in actions:
                    action.report(ctx, action_data)
            else:
                logger.info(f"{self.hash}:{int(time.time() - starttime):04}:False")

class DataWatch(Watch):
    keys = {
        "store" : (str, None),
        "selectors" : (type_list_of_type(dict), list),
        "match" : (lambda x: x if isinstance(x, dict) else {"type" : x}, None),
    }
    template_variables = []

    def render_variables(self, ctx: Context) -> None:
        for x in self.template_variables:
            setattr(self, x, ctx.expand_context(getattr(self, x)))

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        """
        Return the raw data from the Watch
        """
        raise WatchFetchException("Not implemented")

    def select_data(self, ctx: Context, data: typing.List[bytes]) -> typing.List[SelectorItem]:
        """
        Return the selected data from the Watch
        """

        items = [SelectorItem(x) for x in data]
        for selector_kwargs in self.selectors:
            items = Selector.load(**selector_kwargs).execute(ctx, items)
        return items

    def match_items(self, ctx: Context, items: typing.List[SelectorItem]) -> bool:
        """
        Return a boolean indicating whether the processed data matches the configured match
        """
        # By default match on any data, reject no data
        if self.match is None:
            if len(items) == 0:
                return False
            return True

        return Match.load(**self.match).match(ctx, items)

    def run(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        self.render_variables(ctx)
        data = self.select_data(ctx, self.fetch_data(ctx))
        
        # Store data in the context
        ctx.set_variable(self.hash, data)
        if self.store is not None:
            ctx.set_variable(self.store, data)
        # Ensure data variable is available for comment rendering
        ctx.set_variable("data", data)
        
        r = (False, [], [])
        if self.match_items(ctx, data):
            r = (True, self.get_comment(ctx), self.get_data(ctx))
        
        return r

class TrueWatch(DataWatch):
    def match_items(self, ctx: Context, data: typing.List[bytes]) -> bool:
        return True
    
    def fetch_data(self, ctx: Context) -> typing.Iterable[bytes]:
        return []

class GeneratorWatch(DataWatch):
    pass

class RangeWatch(GeneratorWatch):
    default_key = "to"
    keys = {
        "from" : (int, 0),
        "to" : (int, 0),
        "step" : (int, 1),
    }

    def fetch_data(self, _: Context) -> typing.Iterable[bytes]:
        return [str(x).encode() for x in range(getattr(self, "from"), self.to, self.step)]
    
class InfinateWatch(GeneratorWatch):
    def gen(self):
        while True:
            yield b'1'
    
    def fetch_data(self, _: Context) -> typing.Iterable[bytes]:
        return self.gen()

class MultipleWatch(Watch):
    OPERATOR_ALL = ("all", "and")
    OPERATOR_ANY = ("any", "or")
    OPERATOR_LAST = "last"
    OPERATOR_BREAK = "break"

    keys = {
        "operator" : (type_choice(["all", "and", "any", "or", "last"], throw=True), "any")
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Note: This is used solely for testing, there is probably a better way of doing this
        self.watches = []

    def gen(self, ctx: Context) -> Watch:
        raise WatchException("Not Implemented")

    def run(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        comment = []
        data = []
        trigger = False
        _trigger = False

        logger.debug(f"{self.__class__.__name__}: run enter")
        for watch in self.gen(ctx):
            self.watches.append(watch)
            _trigger, _comment, _data = watch.process(ctx)

            if self.operator in MultipleWatch.OPERATOR_ALL:
                if not _trigger:
                    # Early exit on the ALL operator
                    return False, [], []
            
            trigger |= _trigger
            if _trigger:
                comment.extend(_comment)
                data.extend(_data)
            else:
                if self.operator == MultipleWatch.OPERATOR_BREAK:
                    logger.debug(f"{self.__class__.__name__}: run break")
                    break

        if self.operator == MultipleWatch.OPERATOR_LAST:
            comment = [comment[-1]] if len(comment) else []
            data = [data[-1]] if len(data) else []
            trigger = _trigger
        
        if self.comment is not None:
            comment = [*self.get_comment(ctx), comment]

        logger.debug(f"{self.__class__.__name__}: run exit triggered {trigger}")
        return trigger, comment, data

class UrlWatch(DataWatch):
    keys = {
        # "url" : str,
        "method" : (str, "GET"),
        "headers" : (dict, dict),
        "cookies" : (dict, dict),
        "body" : (type_none_or_type(str), None), 
        "code" : (type_none_or_type(int), None),
        "download" : (type_none_or_type(str), None),
        "verify" : (bool, True)
    }
    template_variables = ["url", "headers", "body", "cookies"]

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        ctx.push_variable("URL", self.url)

        # Use a per-context session for URL watches
        s = ctx.get_variable("requests_session")
        if s is None:
            s = requests.session()
            ctx.set_variable("requests_session", s)
        
        if len(self.cookies) > 0:
            domain = urlparse(self.url).hostname
            for k, v in self.cookies.items():
                s.cookies.set(k, v, domain=domain)

        # Filter empty header values
        headers = {k : str(v).strip() for k, v in self.headers.items() if v is not None and len(str(v).strip()) > 0}

        r = s.request(
            self.method,
            self.url,
            headers=headers,
            data=self.body,
            stream=True if self.download is not None else False,
            verify=self.verify)
        
        logger.debug(f"UrlWatch: [{r.status_code} {r.reason}] {self.url}")
        if self.code is not None and r.status_code != self.code:
            raise WatchFetchException(f"Status code {r.status_code} != {self.code}")
        
        ctx.push_variable("status_code", r.status_code)

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
        "env": (dict, dict),
        "cwd": (str, "."),
        "timeout" : (type_one_of(int, str, None), 60),
        "return_code" : (type_none_or_type(int), None),
        "output" : (type_choice(["stdout", "stderr", "both"], default="stdout"), "stdout")
    }
    template_variables = ["cmd", "env", "cwd", "timeout"]

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        shell = [self.shell]
        if self.sudo:
            shell = ["sudo"] + shell

        logger.debug(f"CmdWatch: Executing command: {self.cmd}")
        try:
            p = subprocess.Popen(
                shell, 
                start_new_session=True, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                env={**os.environ, **self.env},
                cwd=self.cwd
            )
            stdout, stderr = p.communicate(self.cmd.encode(), timeout=int(self.timeout) if self.timeout is not None else None)
        except subprocess.TimeoutExpired as e:
            if self.sudo:
                subprocess.run(["sudo", "/bin/kill", "--", f"-{os.getpgid(p.pid)}"])
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            raise WatchFetchException(f"CmdWatch: Command timeout after {self.timeout} seconds") from e

        logger.debug(f"CmdWatch: Return code: {p.returncode}")
        _stdout = ("\n\t" + "\n\t".join(stdout.decode().splitlines()) if len(stdout) else "").strip()
        if len(_stdout):
            logger.debug(f"CmdWatch: Stdout: {_stdout}")
        _stderr = ("\n\t" + "\n\t".join(stderr.decode().splitlines()) if len(stderr) else "").strip()
        if len(_stderr):
            logger.debug(f"CmdWatch: Stderr: {_stderr}")
        if self.return_code is not None and p.returncode != self.return_code:
            raise WatchFetchException(f"CmdWatch: Return code {p.returncode} != {self.return_code}\nStdout:{_stdout}\nStderr:{_stderr}")

        if self.output == "stderr":
            return [stderr]
        elif self.output == "both":
            return [stdout, stderr]
        return [stdout]


class GroupWatch(MultipleWatch):
    keys = {
        "group" : (list, list)
    }

    def gen(self, ctx: Context) -> Watch:
        for x in self.group:
            yield Watch.load(**x)
        
class LoopWatch(MultipleWatch):
    keys = {
        "loop" : (dict, dict),
        "do" : (dict, dict),
        "as" : (str, "loop"),
        "operator" : (str, "or"),
    }

    def gen(self, ctx: Context) -> Watch:
        loop = Watch.load(**self.loop)
        trigger, _, _ = loop.process(ctx)
        
        if trigger:
            for index, data in enumerate(ctx.get_variable(loop.hash)):
                ctx.push_variable("index", index)
                ctx.push_variable(getattr(self, "as"), data.value)

                watch = Watch.load(**self.do)
                # Fixup the loop action hash to ensure it is unique per input
                watch.update_hash({getattr(self, "as") : data.value})
                yield watch
                
                ctx.pop_variable("index")
                ctx.pop_variable(getattr(self, "as"))
    
class ConditionalWatch(MultipleWatch):
    keys = {
        "conditional" : (type_list_of_type(dict), []),
        "operator" : (str, "and"), 
        "then" : (dict, dict),
        "else" : (type_none_or_type(dict), None),
    }

    def gen(self, ctx: Context) -> Watch:
        condition = Watch.load(group=self.conditional, operator=self.operator)
        trigger, _, _ = condition.process(ctx)
        
        if trigger:
            yield Watch.load(**self.then)
        elif getattr(self, "else") is not None:
            yield Watch.load(**getattr(self, "else"))


class OnceWatch(MultipleWatch):
    keys = {
        "once" : (dict, dict),
        "key" : (type_none_or_type(str), None)
    }

    def gen(self, ctx: Context) -> Watch:
        yield Watch.load(**self.once)

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        cache = ctx.get_variable("cache")
        
        hash_key = ctx.expand_context(self.key) if self.key is not None else f"{self.hash}-once"
        logger.debug(f"{self.__class__.__name__}: cache key {hash_key}")
        if cache.has_entry(hash_key):
            return False, [], []

        trigger, comment, data = super().process(ctx)

        if trigger:
            cache.put_entry(hash_key, True)
        return trigger, comment, data

class TemplateWatch(MultipleWatch):
    keys = {
        "template" : (type_list_of_type(str), []),
        "requires" : (list, list),
        "variables" : (dict, dict),
        "body" : (lambda x: x if isinstance(x, (dict, list)) else None, dict)
    }

    @classmethod
    def replace_body(cls, template: dict, body: any) -> typing.Tuple[bool, any]:
        if len(template) == 1 and "body" in template:
            # Replace `body:`
            if template["body"] is None:
                return True, body
            # Append to list of `body: [1, 2, 3]`
            elif isinstance(template["body"], list) and isinstance(body, list):
                return True, [*template["body"], *body]
            # Merge dictionaries of `body: {key: value}`
            elif isinstance(template["body"], dict) and isinstance(body, dict):
                return True, {**template["body"], **body}
            raise WatchException(f"Mismatched template body merge with types {type(template['body']).__name__} and {type(body).__name__}")
        
        for k, v in list(template.items()):
            if isinstance(v, dict):
                # Recurse child dict
                replaced, _template = cls.replace_body(v, body)
                if replaced:
                    return True, {**template, k : _template} # Order preserved
            # TODO: Look into lists as well?

        return False, template

    @classmethod
    def render_template(cls, ctx: Context, templates: typing.List[str], body: dict=None) -> dict:
        body = body or {}
        template = {}
        for x in templates:
            _template = ctx.get_variable("templates").get(x)
            if _template is None:
                raise WatchException(f"Unknown template '{x}'")
            
            # Combine templates, giving later templates precidence
            template = {**template, **_template}

        replaced, template = cls.replace_body(template, body)
        # If a replacement `body:` key is not found in the template stack, attempt to identify the correct resulting watch type
        if not replaced:
            try:
                Watch.get_type(template)
                # Assume that template specifies the subwatch type
                template = {**template, **body}
            except LoadableException:
                # Assume that body specifies the subwatch type
                # Using order of body, apply template keys, then apply body keys
                template = {**body, **template, **body}

        return template

    def gen(self, ctx: Context) -> Watch:
        template = TemplateWatch.render_template(ctx, self.template, body=self.body or self.kwargs)
        
        # Ensure all required template variables are included
        if "requires" in template:
            for r in template["requires"]:
                if not r in self.variables:
                    raise WatchException(f"Template missing required varible '{r}'")
            
            # Remove the meta `requires` key, as it is not a key for the resulting watch
            del template["requires"]
        logger.debug(template)

        # Load and fixup the template hash to ensure it is unique per variable set
        watch = Watch.load(**template)
        watch.update_hash(self.variables)
        yield watch
    
    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        # Push template variables into the context
        ex_variables = ctx.expand_context(self.variables)
        for k, v in ex_variables.items():
            ctx.push_variable(k, v)

        try:
            return super().process(ctx)
        finally:
            # Pop template variables from the context
            for k in self.variables.keys():
                ctx.pop_variable(k)

