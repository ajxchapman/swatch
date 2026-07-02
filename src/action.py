import logging
import json
import os
import typing

import requests

from src.loadable import Loadable, type_choice, type_list_of_type
from src.context import Context

logger = logging.getLogger(__name__)

class ActionException(Exception):
    pass

class Action(Loadable):
    def report(self, ctx: Context, data: dict) -> None:
        raise ActionException("Not Implemented")

    def error(self, ctx: Context, data: dict) -> None:
        pass

class LogAction(Action):
    keys = {
        "level" : (type_choice(["debug", "info", "warning", "error", "critical"], default="info"), "info"),
        "error_level" : (type_choice(["debug", "info", "warning", "error", "critical"], default="error"), "error"),
    }

    def report(self, ctx: Context, data: dict) -> None:
        message = data.get("comment") or json.dumps(data.get("data")) or ""
        comment = "\n\t" + "\n\t".join(message.split("\n"))
        getattr(logger, self.level)(f"Comment: {comment}")
    
    def error(self, ctx: Context, data: dict) -> None:
        getattr(logger, self.error_level)(data.get("error"))

class FileLogAction(LogAction):
    default_key = "file"
    keys = {
        "file" : (str, "swatch.log")
    }
    loggers = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.file = os.path.split(self.file)[-1]

    def get_logger(self, ctx: Context) -> None:
        logname = f"action.file.{self.file}"

        # Have to create the logger lazily, as we don't have access to the context in __init__
        if logname in FileLogAction.loggers:
            return FileLogAction.loggers.get(logname)
        
        log_path = os.path.join(ctx.get_variable("base_dir"), ctx.get_variable("config").get("data_path", "data"))
        os.makedirs(log_path, exist_ok=True)
        
        handler = logging.FileHandler(os.path.join(log_path, self.file))
        formatter = logging.Formatter("%(asctime)s %(levelname)8s %(name)s | %(message)s")
        handler.setFormatter(formatter)

        logger = logging.getLogger(logname)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        FileLogAction.loggers[logname] = logger
        return logger

    def report(self, ctx: Context, data: dict) -> None:
        logger = self.get_logger(ctx)

        for line in data.get("comment").splitlines():
            getattr(logger, self.level)(line)
    
    def error(self, ctx: Context, data: dict) -> None:
        logger = self.get_logger(ctx)
        
        for line in data.get("error").splitlines():
            getattr(logger, self.error_level)(line)

class SlackAction(Action):
    keys = {
        "url" : (str, None),
        "payload" : (dict, {"text" : "MESSAGE"}),
        # Slack auto-splits long messages at an arbitrary character boundary,
        # which breaks links/formatting. Chunk below that limit ourselves,
        # splitting only on newlines.
        "max_length" : (int, 3000),
    }

    def chunk(self, message: str) -> typing.List[str]:
        """
        Split a message into chunks no longer than `max_length`, breaking only
        on newlines so lines (and the links within them) are never split. A
        single line longer than `max_length` is emitted whole (best effort).
        """
        chunks = []
        current = ""
        for line in (message or "").split("\n"):
            if current and len(current) + 1 + len(line) > self.max_length:
                chunks.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        if current:
            chunks.append(current)
        return chunks

    def post(self, message: str) -> None:
        data = json.dumps(self.payload).replace("MESSAGE", json.dumps(message).strip('"'))
        requests.request(
            "POST",
            self.url,
            headers={"content-type" : "application/json"},
            data=data.encode()
        )

    def run(self, message: str) -> None:
        # Send each chunk as its own message, in order
        for chunk in self.chunk(message):
            self.post(chunk)

    def report(self, ctx: Context, data: dict) -> None:
        self.run(data.get("comment"))

    def error(self, ctx: Context, data: dict) -> None:
        self.run(data.get("error"))

class RenderAction(Action):
    default_key = "name"
    keys = {
        "name" : (str, None),
        "id" : (str, "id"),     # Name of the `id` field in the resulting json
        "sort" : (type_list_of_type(str), False)
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = os.path.split(self.name)[-1] + ".json"

    def report(self, ctx: Context, data: dict) -> None:
        render_path = os.path.join(ctx.get_variable("base_dir"), ctx.get_variable("config").get("data_path", "data"))
        os.makedirs(render_path, exist_ok=True)

        render_data = []
        render_path = os.path.join(render_path, self.name)
        if os.path.isfile(render_path):
            with open(render_path, "r") as f:
                render_data = json.load(f)

        # Add or replace the data entries
        for datum in data.get("data", []):
            found = False
            for i, rdata in enumerate(render_data):
                if datum[self.id] == rdata[self.id]:
                    render_data[i] = datum
                    found = True
                    break
            if not found:
                render_data.append(datum)
        
        for key in self.sort or [self.id]:
            render_data.sort(key=lambda x: x.get(key))
        with open(render_path, "w") as f:
            json.dump(render_data, f, indent=4)