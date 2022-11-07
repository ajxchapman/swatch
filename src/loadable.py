from __future__ import annotations
import hashlib
import logging
import typing
import types

logger = logging.getLogger(__name__)

class LoadableException(Exception):
    pass

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

class Loadable:
    __loadables = set()
    __classes = {}
    __class_keys = {}

    @classmethod
    def load(cls, **kwargs) -> Loadable:
        # Load default key values from the Loadable subclasses
        if not cls.__name__ in cls.__loadables:
            cls.__loadables.add(cls.__name__)

            for c in all_subclasses(cls):
                scls_name = (cls.__name__ + "_" + c.__name__.replace(cls.__name__, "")).lower()
                cls.__classes[scls_name] = c

                # Add the classname as a default key
                cls.__class_keys[scls_name] = {
                    c.__name__.replace(cls.__name__, "").lower(): (object, None)
                }
                for x in c.__mro__[::-1]:
                    cls.__class_keys[scls_name] = {**cls.__class_keys.get(scls_name, {}), **getattr(x, "keys", {})}

        # Obtain the loadable type from the "type" kwarg or the first kwarg
        # Allows for definitions such as:
        #   - type: "regex"
        #     value: ".*"
        # Or
        #   - regex: ".*"
        ltype = kwargs.get("type")
        if ltype is not None:
            lvalue = None
            del kwargs["type"]
        else:
            ltype = next(kwargs.keys().__iter__())
            lvalue = kwargs[ltype]

        lctype = f"{cls.__name__}_{ltype}".lower()
        if not lctype in cls.__classes:
            raise LoadableException(f"Unknown {cls.__name__} class {ltype}")

        lcls = cls.__classes[lctype]
        lcls_keys = cls.__class_keys[lctype]

        logger.debug(f"Loading {cls.__name__} type {lctype}")
        logger.debug(f"\tKeys: {lcls_keys}")
        logger.debug(f"\tKwargs: {kwargs}")
        
        # If the loadable defines a default key, set the "type" value to the default_key name
        if lvalue is not None and hasattr(lcls, "default_key"):
            del kwargs[ltype]
            kwargs[lcls.default_key] = lvalue

        # Initialise loadable kwargs
        lkwargs = {}
        for k, v in lcls_keys.items():
            ktype, kdefault = v if isinstance(v, tuple) else (type(v), v)
            if k in kwargs:
                # Cast as the correct type
                if ktype is None:
                    raise LoadableException(f"Unexpected argument '{k}'")
                
                if isinstance(ktype, types.FunctionType):
                    lkwargs[k] = ktype(kwargs[k])
                else:
                    lkwargs[k] = kwargs[k] if isinstance(kwargs[k], ktype) else ktype(kwargs[k])
            else:
                # If the default is a callable, call it
                if isinstance(kdefault, (type, types.FunctionType)):
                    kdefault = kdefault()
                lkwargs[k] = kdefault
        
        lobj = lcls(**lkwargs)
        lobj.hashobj = hash_args(lkwargs, skip_keys=getattr(lcls, "hash_skip", []))
        lobj.hash = lobj.hashobj.hexdigest()
        return lobj

    def update_hash(self, arg: object) -> None:
        self.hashobj = hash_args(arg, self.hashobj)
        self.hash = self.hashobj.hexdigest()

    def __init__(self, **kwargs):
        # Generic init method to set the kwargs to instance variables
        for k, v in kwargs.items():
            setattr(self, k, v)