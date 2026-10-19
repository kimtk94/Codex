"""Offline guard tests for the private helper AST bridge; synthetic Python only."""
from __future__ import annotations

import ast
import unittest

from g16_private_real_helper_bridge import (
    safe_function, stripped_copy, callable_name, SAFE_BUILTINS,
)

def get_function(src: str):
    tree = ast.parse(src)
    return next(x for x in tree.body if isinstance(x, ast.FunctionDef))

class G16PrivateBridgeGuardTests(unittest.TestCase):
    def test_simple_stripping_function_static_allowed(self):
        f=get_function("def clean_text(x):\n    return str(x).strip()\n")
        self.assertTrue(safe_function(f))
        clean=stripped_copy(f)
        env={"__builtins__":SAFE_BUILTINS}
        exec(compile(ast.Module(body=[clean],type_ignores=[]),"<synthetic>","exec"),env)
        self.assertEqual(env["clean_text"]("  TEST-A  "), "TEST-A")

    def test_local_normalizer(self):
        f=get_function("def normalize_text(x):\n    return clean_text(x).lower()\n")
        self.assertTrue(safe_function(f))

    def test_raw_database_open_denied(self):
        f=get_function("def clean_text(x):\n    return sqlite3.connect('/tmp/real.db')\n")
        self.assertFalse(safe_function(f))

    def test_network_send_denied(self):
        f=get_function("def clean_text(x):\n    return requests.post('https://example.test')\n")
        self.assertFalse(safe_function(f))

    def test_dynamic_import_denied(self):
        f=get_function("def clean_text(x):\n    return __import__('os')\n")
        self.assertFalse(safe_function(f))

    def test_builtin_file_open_denied(self):
        f=get_function("def clean_text(x):\n    return open('/etc/passwd').read()\n")
        self.assertFalse(safe_function(f))

    def test_decorator_denied(self):
        f=get_function("@decorator\ndef clean_text(x):\n    return str(x)\n")
        self.assertFalse(safe_function(f))

    def test_effectful_default_denied(self):
        f=get_function("def clean_text(x=run_command()):\n    return x\n")
        self.assertFalse(safe_function(f))

    def test_nested_import_denied(self):
        f=get_function("def clean_text(x):\n    import os\n    return x\n")
        self.assertFalse(safe_function(f))

    def test_lambda_denied(self):
        f=get_function("def clean_text(x):\n    fn=lambda y:y\n    return fn(x)\n")
        self.assertFalse(safe_function(f))

    def test_unknown_method_denied(self):
        f=get_function("def clean_text(x):\n    return x.update_server()\n")
        self.assertFalse(safe_function(f))

    def test_no_returned_function_source(self):
        f=get_function("def clean_text(x):\n    return 'CONFIDENTIAL_CONSTANT'\n")
        self.assertTrue(safe_function(f))
        self.assertNotIn("CONFIDENTIAL_CONSTANT", callable_name(f))


    def test_direct_dunder_attribute_denied(self):
        f=get_function("def clean_text(x):\n    return x.__class__\n")
        self.assertFalse(safe_function(f))

    def test_python_class_introspection_denied(self):
        f=get_function("def clean_text(x):\n    return x.__class__.__mro__\n")
        self.assertFalse(safe_function(f))

    def test_module_private_attribute_denied(self):
        f=get_function("def clean_text(x):\n    return re.__dict__\n")
        self.assertFalse(safe_function(f))

    def test_plain_unapproved_attribute_denied(self):
        f=get_function("def clean_text(x):\n    return x.remote_api\n")
        self.assertFalse(safe_function(f))

    def test_explicit_re_function_still_allowed(self):
        f=get_function("def clean_text(x):\n    return re.fullmatch('TEST', x) is not None\n")
        self.assertTrue(safe_function(f))


if __name__=="__main__":
    unittest.main(verbosity=2)
