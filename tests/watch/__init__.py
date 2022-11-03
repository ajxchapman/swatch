import typing
from xml.sax.handler import feature_external_ges
from src.template import template_render

from src.watch import Watch, Context
from src.match import Match

class CountWatch(Watch):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.count = 0

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        self.count += 1
        return []

class DataWatch(Watch):
    keys = {
        "data" : (list, list)
    }

    def fetch_data(self, ctx: Context) -> typing.List[bytes]:
        return ctx.expand_context(self.data)

class TrueMatch(Match):
    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        return True

class FalseMatch(Match):
    def match(self, ctx: Context, data: typing.List[bytes]) -> bool:
        return False