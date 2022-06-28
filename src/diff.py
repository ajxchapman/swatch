import difflib

from src.loadable import Loadable

class DiffException(Exception):
    pass

class Diff(Loadable):
    def diff(self, old, new):
        raise DiffException("Not Implemented")

class NewDiff(Diff):
    def diff(self, old, new):
        oldset = set(old)
        new_entries = []
        for x in new:
            if not x in oldset:
                new_entries.append(x)
        
        return new_entries

class UnifiedDiff(Diff):
    def diff(self, old, new):
        return difflib.diff_bytes(difflib.unified_diff, old, new)

class HashDiff(Diff):
    def diff(self, old, new):
        pass