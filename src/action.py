import logging
import json
import os
import requests

from src.loadable import Loadable
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
        "level" : (lambda x: x if x in ["debug", "info", "warning", "error", "critical"] else "info", "info"),
        "error_level" : (lambda x: x if x in ["debug", "info", "warning", "error", "critical"] else "error", "error"),
    }

    def report(self, ctx: Context, data: dict) -> None:
        getattr(logger, self.level)(data.get("comment"))
    
    def error(self, ctx: Context, data: dict) -> None:
        getattr(logger, self.error_level)(data.get("error"))

class FileLogAction(LogAction):
    default_key = "file"
    keys = {
        "file" : (str, "swatch.log")
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.file = os.path.split(self.file)[-1]
        self.logger = None

    def create_logger(self, ctx: Context) -> None:
        # Have to create the logger lazily, as we don't have access to the context in __init__
        if self.logger is not None:
            return
        
        log_path = os.path.join(ctx.get_variable("base_dir"), ctx.get_variable("config").get("log_path", "logs"))
        os.makedirs(log_path, exist_ok=True)
        
        handler = logging.FileHandler(os.path.join(log_path, self.file))
        formatter = logging.Formatter("%(asctime)s %(levelname)8s %(name)s | %(message)s")
        handler.setFormatter(formatter)

        self.logger = logging.getLogger("action.file")
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

    def report(self, ctx: Context, data: dict) -> None:
        self.create_logger(ctx)
        getattr(self.logger, self.level)(data.get("comment"))
    
    def error(self, ctx: Context, data: dict) -> None:
        self.create_logger(ctx)
        getattr(self.logger, self.error_level)(data.get("error"))

class SlackAction(Action):
    keys = {
        "url" : (str, None),
        "payload" : (dict, {"text" : "MESSAGE"})
    }
    
    def run(self, message: str) -> None:
        data = json.dumps(self.payload).replace("MESSAGE", json.dumps(message).strip('"'))
        r = requests.request(
            "POST",
            self.url,
            headers={"content-type" : "application/json"},
            data=data.encode()
        )

    def report(self, ctx: Context, data: dict) -> None:
        self.run(data.get("comment"))
    
    def error(self, ctx: Context, data: dict) -> None:
        self.run(data.get("error"))

class RenderAction(Action):
    default_key = "name"
    keys = {
        "name" : (str, None),
        "id" : (str, "id"),
        "sort" : (str, False)
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = os.path.split(self.name)[-1] + ".json"

    def report(self, ctx: Context, data: dict) -> None:
        render_path = os.path.join(ctx.get_variable("base_dir"), ctx.get_variable("config").get("render_path", "render"))
        os.makedirs(render_path, exist_ok=True)

        render_data = []
        render_path = os.path.join(render_path, self.name)
        if os.path.isfile(render_path):
            with open(render_path, "r") as f:
                render_data = json.load(f)

        print("report", render_path)

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
        
        render_data.sort(key=lambda x: x.get(self.sort or self.id))
        with open(render_path, "w") as f:
            json.dump(render_data, f, indent=4)