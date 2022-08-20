import typing

from src.template import template_render

class Context:
    def __init__(self):
        self.stack_variables = set()
        self._variables = {}

    def keys(self):
        return self._variables.keys()

    def __getitem__(self, key: typing.Any) -> typing.Any:
        return self.get_variable(key)

    def push_variable(self, key: str, value: typing.Any) -> None:
        self.stack_variables.add(key)
        self._variables.setdefault(key, []).append(value)

    def pop_variable(self, key: str) -> typing.Any:
        v = self._variables[key].pop()
        if len(self._variables[key]) == 0:
            self.stack_variables.remove(key)
            del self._variables[key]
        return v

    def set_variable(self, key: str, value: typing.Any) -> None:
        self._variables[key] = value

    def get_variable(self, key: str, default: typing.Any=None) -> typing.Any:
        if key in self.stack_variables:
            return self._variables.get(key, [default])[-1]
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