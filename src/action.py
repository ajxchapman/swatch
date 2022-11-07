import logging
import json
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
    def report(self, ctx: Context, data: dict) -> None:
        logger.info(data.get("comment"))
    
    def error(self, ctx: Context, data: dict) -> None:
        logger.error(data.get("error"))

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