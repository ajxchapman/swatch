import unittest

from src.template import template_render

class TestTemplate(unittest.TestCase):
    def test_basic(self):
        t = """Hello {{ value }}"""
        self.assertEqual(template_render(t, value="World"), "Hello World")

    def test_int(self):
        t = """Hello {{ value }}"""
        self.assertEqual(template_render(t, value=123), "Hello 123")

    def test_bytes(self):
        t = """Hello {{ value }}"""
        self.assertEqual(template_render(t, value=b'World'), "Hello World")

    def test_list_empty(self):
        t = """Hello {{ value }}"""
        self.assertEqual(template_render(t, value=[]), "Hello ")

    def test_list_single(self):
        t = """Hello {{ value }}"""
        self.assertEqual(template_render(t, value=["World"]), "Hello World")
    
    def test_list_multiple(self):
        t = """Hello {{ value }}"""
        self.assertEqual(template_render(t, value=["World", "123"]), "Hello ['World', '123']")

    def test_dict_empty(self):
        t = """Hello {{ value }}"""
        self.assertEqual(template_render(t, value={}), "Hello ")

    def test_unixtime(self):
        t = """Hello {{ unixtime }}"""
        self.assertRegex(template_render(t), "Hello [0-9]+")