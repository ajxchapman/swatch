import unittest

from src.match import Match, MatchException
from src.context import Context

class TestCondMatch(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx = Context()
        self.ctx.set_variable("v1", 123)
        self.ctx.set_variable("i2", 456)
    
    def test_lt(self):
        m: Match = Match.load(cond="lt 10")
        self.assertEqual(m.match(self.ctx, [b'1']), True)
        self.assertEqual(m.match(self.ctx, [b'11']), False)

    def test_lt_exception(self):
        m: Match = Match.load(cond="lt 10")
        with self.assertRaises(MatchException):
            m.match(self.ctx, [b'abc'])

        m: Match = Match.load(cond="lt abc")
        with self.assertRaises(MatchException):
            m.match(self.ctx, [b'10'])
    
    def test_eq_int(self):
        m: Match = Match.load(cond="eq 10")
        self.assertEqual(m.match(self.ctx, [b'10']), True)
        self.assertEqual(m.match(self.ctx, [b'11']), False)
    
    def test_eq_str(self):
        m: Match = Match.load(cond="eq abc")
        self.assertEqual(m.match(self.ctx, [b'abc']), True)
        self.assertEqual(m.match(self.ctx, [b'def']), False)
    
    def test_neq_int(self):
        m: Match = Match.load(cond="neq 10")
        self.assertEqual(m.match(self.ctx, [b'10']), False)
        self.assertEqual(m.match(self.ctx, [b'11']), True)
    
    def test_neq_str(self):
        m: Match = Match.load(cond="neq abc")
        self.assertEqual(m.match(self.ctx, [b'abc']), False)
        self.assertEqual(m.match(self.ctx, [b'def']), True)

    def test_eq_static(self):
        m: Match = Match.load(cond="1 eq 1")
        self.assertEqual(m.match(self.ctx, [b'abc']), True)
        self.assertEqual(m.match(self.ctx, [b'def']), True)

    def test_eq_ctx(self):
        m: Match = Match.load(cond="eq {{ v1 }}")
        self.assertEqual(m.match(self.ctx, [b'123']), True)
        self.assertEqual(m.match(self.ctx, [b'456']), False)