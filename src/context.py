from __future__ import annotations
import typing

from src.template import template_render

class ContextException(Exception):
    pass

class Context:
    def __init__(self):
        self.frames = [{"_frameId" : "root"}]
        self._variables = {}

    def keys(self):
        keys = set(self._variables.keys())
        for frame in self.frames:
            keys.update(frame.keys())
        return list(keys)

    def __getitem__(self, key: typing.Any) -> typing.Any:
        return self.get_variable(key)

    def push_frame(self, id: str | None=None) -> None:
        self.frames.append({"_frameId" : id})

    def pop_frame(self, id: str | None=None) -> None:
        frame = self.frames.pop()
        if frame["_frameId"] != id:
            raise ContextException(f"Stack frames do not match up {id} != {frame['id']}")

    def push_variable(self, key: str, value: typing.Any) -> None:
        if len(self.frames) == 0:
            raise ContextException("No context frame to push to")
        
        self.frames[-1].setdefault(key, []).append(value)

    def pop_variable(self, key: str) -> typing.Any:
        if len(self.frames) == 0:
            raise ContextException("No context frame to push to")
        
        v = self.frames[-1][key].pop()
        if len(self.frames[-1][key]) == 0:
            del self.frames[-1][key]
        return v

    def set_variable(self, key: str, value: typing.Any) -> None:
        self._variables[key] = value

    def get_variable(self, key: str, default: typing.Any=None) -> typing.Any:
        """
        Get the most recent value of a variable from the context
        """
        for frame in self.frames:
            if key in frame:
                return frame[key][-1]
        return self._variables.get(key, default)

    def expand_context(self, value: typing.Any) -> typing.Any:
        if isinstance(value, str):
            if "{" in value:
                return template_render(value, self)
        elif isinstance(value, list):
            return [self.expand_context(x) for x in value]
        elif isinstance(value, dict):
            return {self.expand_context(k) : self.expand_context(v) for k, v in value.items()}
        return value