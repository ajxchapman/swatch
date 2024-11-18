import unittest
import yaml

from src.context import Context
from src.selector import Selector




class TestSubSelector(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
    
    def test_returns_singular(self):
        test_schema = """
sub:
  - split: ','
  - pick: [1, 2]
  - join: ','
"""
        s: Selector = Selector.load(**yaml.safe_load(test_schema))
        data = [b'1,2,3,4,5', b'6,7,8,9,10']

        result = s.execute(self.ctx, data)
        self.assertListEqual(result, [b'2,3', b'7,8'])

    def test_returns_multiple(self):
        test_schema = """
sub:
  - split: ','
  - pick: [1, 2]
"""
        s: Selector = Selector.load(**yaml.safe_load(test_schema))
        data = [b'1,2,3,4,5', b'6,7,8,9,10']

        result = s.execute(self.ctx, data)
        self.assertListEqual(result, [b'2', b'3', b'7', b'8'])
