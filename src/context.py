from jinja2 import Environment, BaseLoader

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

    def finalize(self, value):
        if value is None:
            return ""
        elif isinstance(value, bytes):
            return value.decode()
        elif isinstance(value, list):
            if len(value) == 0:
                return ""
            if len(value) == 1:
                return self.finalize(value[0])
        elif isinstance(value, dict):
            if len(value) == 0:
                return ""
        return value

    def expand_context(self, value):
        def match(m):
            k, v = (m.group(1).split(":") + [None])[:2]
            return str(self.get_variable(k, v) or "")
        if isinstance(value, str):
            if "{" in value:
                return Environment(loader=BaseLoader(), finalize=self.finalize).from_string(value).render(**self.variables)
        elif isinstance(value, list):
            return [self.expand_context(x) for x in value]
        elif isinstance(value, dict):
            return {self.expand_context(k) : self.expand_context(v) for k, v in value.items()}
        return value