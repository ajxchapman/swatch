from email.policy import default
import typing

from src.watch import Watch, DataWatch, Context, WatchException
from src.match import Match

class CountWatch(DataWatch):
    class_count = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.count = 0

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        self.count += 1
        self.__class__.class_count += 1
        return [str(self.count).encode()]

class StaticWatch(DataWatch):
    default_key = "data"
    keys = {
        "data" : (list, list)
    }

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        return ctx.expand_context(self.data)

class ThrowWatch(Watch):
    def run(self, ctx: Context) -> typing.Tuple[bool, typing.List[str], typing.List[dict]]:
        raise WatchException()

class TrueMatch(Match):
    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        return True

class FalseMatch(Match):
    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        return False