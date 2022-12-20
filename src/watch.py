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
from src.loadable import Loadable, type_none_or_type, type_list_of_type, type_choice
from src.match import Match
from src.selector import Selector

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

    def run(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        raise WatchException("Not implemented")
    
    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        """
        Entrypoint into an individual (potentially nested) watch.
        Returns a tuple of (action_trigger, action_comment, action_data) with `action_trigger` True if the action_data of the Watch should be reported, False otherwise
        """
        cache = ctx.get_variable("cache")
        # Set the last run time
        cache.put_entry(f"{self.hash}-executed", ctx.get_variable("starttime"))
        ctx.push_variable("hash", self.hash)

        try:
            # Execute the `before` step within the try block to ensure exception halt processing
            for watch in self.before:
                watch = Watch.load(**{**watch, "match": "none"})
                watch.process(ctx)
            
            trigger, comment, data = self.run(ctx)
            
        except:
            failure_count = cache.get_entry(f"{self.hash}-failures") or 0
            cache.put_entry(f"{self.hash}-failures", failure_count + 1)
            raise
        else:
            # Clear any previous failure count
            cache.put_entry(f"{self.hash}-failures", 0)

            if not trigger:
                return False, [], []
            
            # Record the last triggered time
            cache.put_entry(f"{self.hash}-triggered", ctx.get_variable("starttime"))
            return trigger, comment, data
        finally:
            # Execute the `after` step within the finally block to ensure it is always executed
            # Ignore exceptions thrown by the `after` block
            try:
               for watch in self.after:
                    watch = Watch.load(**{**watch, "match": "none"})
                    watch.process(ctx)
            except Exception as e:
                logger.debug(e, exc_info=1)
            ctx.pop_variable("hash")

    def execute(self, ctx: Context) -> None:
        """
        Entrypoint into the top level watch
        """
        starttime =  time.time()
        ctx.set_variable("starttime", starttime)
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
            failure_count = cache.get_entry(f"{self.hash}-failures")
            
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

    def run(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        data = self.select_data(ctx, self.fetch_data(ctx))
        trigger = self.match_data(ctx, data)

        if not trigger:
            return False, [], []
        
        # Store watch data in the context
        if self.store is not None:
            ctx.set_variable(self.store, data)
        ctx.set_variable(self.hash, data)
        
        ctx.push_variable("data", data)
        r = (trigger, self.get_comment(ctx), self.get_data(ctx))
        ctx.pop_variable("data")
        return r

class MultipleWatch(Watch):
    OPERATOR_ALL = ("all", "and")
    OPERATOR_ANY = ("any", "or")
    OPERATOR_LAST = "last"

    keys = {
        "operator" : (type_choice(["all", "and", "any", "or", "last"], throw=True), "any")
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.watches = []

    def gen(self, ctx: Context) -> Watch:
        raise WatchException("Not Implemented")

    def run(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        comment = []
        data = []
        trigger = False
        _trigger = False

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

        if self.operator == MultipleWatch.OPERATOR_LAST:
            comment = [comment[-1]] if len(comment) else []
            data = [data[-1]] if len(data) else []
            trigger = _trigger
        
        if self.comment is not None:
            comment = [*self.get_comment(ctx), comment]
        return trigger, comment, data

class UrlWatch(DataWatch):
    keys = {
        "method" : (str, "GET"),
        "headers" : (dict, dict),
        "cookies" : (dict, dict),
        "data" : (str, None), 
        "code" : (type_none_or_type(int), 200),
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
        "env": (dict, dict),
        "cwd": (str, "."),
        "timeout" : (type, 30),
        "return_code" : (type_none_or_type(int), 0),
        "output" : (type_choice(["stdout", "stderr", "both"], default="stdout"), "stdout")
    }

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        ex_cmd = ctx.expand_context(self.cmd)
        ex_env = ctx.expand_context({**os.environ, **self.env})
        ex_cwd = ctx.expand_context(self.cwd)
        shell = [self.shell]
        if self.sudo:
            shell = ["sudo"] + shell

        logger.debug(f"CmdWatch: Executing command: {ex_cmd}")
        try:
            p = subprocess.Popen(
                shell, 
                start_new_session=True, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                env=ex_env,
                cwd=ex_cwd
            )
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


class GroupWatch(MultipleWatch):
    default_key = "group"
    keys = {
        "group" : (list, list)
    }

    def gen(self, ctx: Context) -> Watch:
        for x in self.group:
            yield Watch.load(**x)
        

class LoopWatch(MultipleWatch):
    default_key = "loop"
    keys = {
        "loop" : (dict, dict),
        "do" : (dict, dict),
        "as" : (str, "loop"),
        "operator" : (str, "or"),
    }

    def gen(self, ctx: Context) -> Watch:
        loop = Watch.load(**{**self.loop, "version": self.version})
        trigger, _, _ = loop.process(ctx)
        
        if trigger:
            for data in ctx.get_variable(loop.hash):
                ctx.push_variable(getattr(self, "as"), data)
                
                watch = Watch.load(**self.do)
                # Fixup the loop action hash to ensure it is unique per input
                watch.update_hash({getattr(self, "as") : data})
                yield watch
                
                ctx.pop_variable(getattr(self, "as"))
    
class ConditionalWatch(MultipleWatch):
    keys = {
        "conditional" : (type_list_of_type(dict), []),
        "operator" : (str, "and"), 
        "then" : (dict, dict)
    }

    def gen(self, ctx: Context) -> Watch:
        condition = Watch.load(group=self.conditional, operator=self.operator, version=self.version)
        trigger, _, _ = condition.process(ctx)
        
        if trigger:
            yield Watch.load(**{**self.then, "version": self.version})


class OnceWatch(MultipleWatch):
    keys = {
        "once" : (dict, dict)
    }

    def gen(self, ctx: Context) -> Watch:
        yield Watch.load(**self.once)

    def process(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        cache = ctx.get_variable("cache")
        if cache.get_entry(f"{self.hash}-once") is not None:
            return False, [], []

        trigger, comment, data = super().process(ctx)

        if trigger:
            cache.put_entry(f"{self.hash}-once", True)
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
            template_type = Watch.get_type(template)
            if template_type is not None:
                # Assume that template specifies the subwatch type
                template = {**template, **body}
            else:
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

