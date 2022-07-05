from src.template import template_render

class Context:
    def __init__(self):
        self.output = None
        self.outputs = []
        self.variables = {}

    def add_output(self, output):
        self.output = output
        self.outputs.append(output)

    def set_variable(self, key: str, value: object) -> None:
        self.variables[key] = value

    def get_variable(self, key: str, default: object=None) -> object:
        return self.variables.get(key, default)

    def expand_context(self, value):
        if isinstance(value, str):
            if "{" in value:
                return template_render(value, self.variables)
        elif isinstance(value, list):
            return [self.expand_context(x) for x in value]
        elif isinstance(value, dict):
            return {self.expand_context(k) : self.expand_context(v) for k, v in value.items()}
        return value