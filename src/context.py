class WatchContext:
    def __init__(self):
        self.output = None
        self.outputs = []
        self.variables = {}

    def add_output(self, output):
        self.output = output
        self.outputs.append(output)

    def set_variable(self, key: str, value: object) -> None:
        self.variables[key] = value

    def expand_context(self, value):
        pass