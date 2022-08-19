import difflib
import typing

from src.loadable import Loadable

class DiffException(Exception):
    pass

class Diff(Loadable):
    def diff(self, old: typing.List[bytes], new: typing.List[bytes]) -> typing.Tuple[typing.List[bytes], typing.List[bytes]]:
        raise DiffException("Not Implemented")

class NewDiff(Diff):
    def diff(self, old: typing.List[bytes], new: typing.List[bytes]) -> typing.Tuple[typing.List[bytes], typing.List[bytes]]:
        old_set = set(old)

        # Iterate instead of `difference` to preserve order
        new_entries = []
        for x in new:
            if not x in old_set:
                new_entries.append(x)
        
        return (new_entries, list(old_set.union(new_entries)))

class UnifiedDiff(Diff):
    def diff(self, old: typing.List[bytes], new: typing.List[bytes]) -> typing.Tuple[typing.List[bytes], typing.List[bytes]]:
        return (list(difflib.diff_bytes(difflib.unified_diff, old, new)), new)