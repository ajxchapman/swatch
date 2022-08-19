import json

from jinja2 import Environment, BaseLoader

env = None
def init_env():
    global env
    if env is None:
        env = Environment(
            loader=BaseLoader(), 
            finalize=finalize,
            trim_blocks=True,
            lstrip_blocks=True
        )
        env.filters["json"] = lambda x: json.loads(x if isinstance(x, str) else x.decode())
        env.filters["b64encode"] = lambda x: base64.b64encode(x.encode() if isinstance(x, str) else x)
        env.filters["b64decode"] = lambda x: base64.b64decode(x)
    return env
        
def finalize(value):
    if value is None:
        return ""
    elif isinstance(value, bytes):
        return value.decode()
    elif isinstance(value, list):
        if len(value) == 0:
            return ""
        if len(value) == 1:
            return finalize(value[0])
    elif isinstance(value, dict):
        if len(value) == 0:
            return ""
    return value

def template_render(template, *args, **kwargs):
    _template = init_env().from_string(template)
    
    _args = {}
    for x in args:
        _args.update(x)
    _args.update(kwargs)
    return _template.render(_args)