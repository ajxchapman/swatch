from __future__ import annotations
import hashlib


class LoadableException(Exception):
    pass

class Loadable:
    __loadables = set()
    __classes = {}
    __class_keys = {}

    @classmethod
    def load(cls, **kwargs) -> Loadable:
        # Load default key values from the Loadable subclasses
        if not cls.__name__ in cls.__loadables:
            cls.__loadables.add(cls.__name__)

            for c in cls.__subclasses__():
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
                lkwargs[k] = kwargs[k] if isinstance(kwargs[k], ktype) else ktype(kwargs[k])
            else:
                lkwargs[k] = kdefault
        return lcls(**lkwargs)

    def __init__(self, **kwargs):
        hash = hashlib.sha256()
        # Generic init method to set the kwargs to instance variables
        for k, v in kwargs.items():
            hash.update(k.encode())
            hash.update(repr(v).encode())
            setattr(self, k, v)
        self.hash = hash.hexdigest()