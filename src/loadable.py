from __future__ import annotations
import hashlib
import logging
import typing
import types

logger = logging.getLogger(__name__)

RESERVED_KEYS = ["kwargs", "type"]

class LoadableException(Exception):
    pass

def type_list_of_type(type: typing.Type) -> typing.Callable[[typing.Any], typing.Any]:
    def inner(arg: typing.Any):
        if not isinstance(arg, list):
            arg = [arg]
        
        for x in arg:
            if not isinstance(x, type):
                raise LoadableException(f"Argument '{x}' is not of type {type.__name__}")
        return arg
    return inner

def type_none_or_type(type: typing.Type) -> typing.Callable[[typing.Any], typing.Any]:
    def inner(arg: typing.Any):
        return arg if arg is None else type(arg)
    return inner

def type_choice(options: typing.List[typing.Any], default: typing.Any=None, throw: bool=False) -> typing.Callable[[typing.Any], typing.Any]:
    def inner(arg: typing.Any):
        if arg in options:
            return arg
        
        if throw:
            raise LoadableException(f"Argument '{arg}' is not one of {options}")
        return default
    
    return inner

def hash_args(arg: object, hash: object=None, skip_keys: typing.List[bytes]=[]) -> object:
    if hash is None:
        hash = hashlib.sha256()
    if isinstance(arg, list):
        hash.update(b'[')
        [(hash_args(x, hash, skip_keys), hash.update(b',')) for x in arg]
        hash.update(b']')
    elif isinstance(arg, dict):
        hash.update(b'{')
        [(hash_args(k, hash, skip_keys), hash.update(b':'), hash_args(v, hash, skip_keys), hash.update(b',')) for k, v in arg.items() if not k in skip_keys]
        hash.update(b'}')
    else:
        hash.update(b's')
        hash.update(str(arg).encode())
    return hash

def all_subclasses(cls):
    return set(cls.__subclasses__()).union([s for c in cls.__subclasses__() for s in all_subclasses(c)])

_loadables = set()
_classes = {}

class Loadable:
    @classmethod
    def get_type(cls, kwargs: dict) -> type[Loadable]:
        # Obtain the loadable type from the "type" kwarg or the first kwarg
        # Allows for definitions such as:
        #   - type: "regex"
        #     value: ".*"
        # Or
        #   - regex: ".*"
        ltype = None
        if "type" in kwargs:
            ltype =  kwargs["type"]
        else:
            # If a `type` hint isnt provided, assume the type is in the first key that is not in the tope level class `type_determination_skip` list
            for x in kwargs.keys():
                if not x in getattr(cls, "type_determination_skip", []):
                    ltype = x
                    break

        lctype = f"{cls.__name__}_{ltype}".lower()
        if not lctype in _classes:
            raise LoadableException(f"Unknown {cls.__name__} class {ltype}")

        return _classes.get(lctype)

    @classmethod
    def prepare(cls) -> None:
        if not cls.__name__ in _loadables:
            _loadables.add(cls.__name__)
            cls.loadable_type = cls.__name__.lower()

            for subcls in all_subclasses(cls):
                subcls.loadable_name = subcls.__name__.replace(cls.__name__, "").lower()
                subcls.loadable_type = f"{cls.loadable_type}_{subcls.loadable_name}"

                _classes[subcls.loadable_type] = subcls

                # Add the classname as a default key with a default type hint and value
                subcls.loadable_keys = {
                    subcls.loadable_name: (object, None)
                }

                # Traverse down the class inheritence stack merging any found `keys` dictionaries
                for x in subcls.__mro__[::-1]:
                    subcls.loadable_keys = {**subcls.loadable_keys, **getattr(x, "keys", {})}
            
                # Check no reserved names are used in the discovered class keys
                for k in subcls.loadable_keys.keys():
                    if k in RESERVED_KEYS:
                        raise LoadableException(f"Loadable {cls.__name__} uses reserved key '{k}'")

    @classmethod
    def load(cls, **kwargs) -> Loadable:
        cls.prepare()

        # Discern the loadable type
        loadable_cls = cls.get_type(kwargs)
        logger.debug(f"Loading {cls.__name__} type {loadable_cls}")

        # If the `type` hint was used in kwargs, remove it
        if "type" in kwargs:
            del kwargs["type"]

        # If the loadable defines a default key, set the `loadable_name` value to the default_key name
        default_value = kwargs.get(loadable_cls.loadable_name)
        if default_value is not None and hasattr(loadable_cls, "default_key"):
            del kwargs[loadable_cls.loadable_name]
            kwargs[loadable_cls.default_key] = default_value

        # Initialise loadable kwargs
        lkwargs = {}
        for k, v in loadable_cls.loadable_keys.items():
            ktype, kdefault = v if isinstance(v, tuple) else (type(v), v)
            if k in kwargs:
                # Cast as the correct type
                if ktype is None:
                    raise LoadableException(f"Unexpected argument '{k}'")
                
                if isinstance(ktype, types.FunctionType):
                    # Exceptions raised it ktype will bubble
                    lkwargs[k] = ktype(kwargs[k])
                else:
                    if isinstance(kwargs[k], ktype):
                        lkwargs[k] = kwargs[k]
                    # Attempt to cast basic types
                    elif ktype in {str, int, bool}:
                        lkwargs[k] = ktype(kwargs[k])
                    else:
                        raise LoadableException(f"Unable to cast argument '{k}' with value '{kwargs[k]}' as type '{ktype.__name__}'")
                
                # Remove assigned keys from the supplied arguments
                del kwargs[k]
            else:
                # If the default is a callable, call it
                if isinstance(kdefault, (type, types.FunctionType)):
                    kdefault = kdefault()
                lkwargs[k] = kdefault

        # Assign remaining kwargs to a kwargs key
        lkwargs["kwargs"] = kwargs
        
        lobj = loadable_cls(**lkwargs)
        lobj.hashobj = hash_args(lkwargs, skip_keys=getattr(loadable_cls, "hash_skip", []))
        lobj.hash = lobj.hashobj.hexdigest()
        return lobj

    def update_hash(self, arg: object) -> None:
        self.hashobj = hash_args(arg, self.hashobj)
        self.hash = self.hashobj.hexdigest()

    def __init__(self, **kwargs):
        # Generic init method to set the kwargs to instance variables
        for k, v in kwargs.items():
            setattr(self, k, v)