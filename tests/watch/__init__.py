import typing

from src.watch import Watch, WatchContext
from src.match import Match

class CountWatch(Watch):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.count = 0

    def fetch_data(self, ctx: WatchContext) -> typing.List[bytes]:
        self.count += 1
        return []

class TrueMatch(Match):
    def match(self, ctx: WatchContext, data: typing.List[bytes]) -> bool:
        return True

class FalseMatch(Match):
    def match(self, ctx: WatchContext, data: typing.List[bytes]) -> bool:
        return False