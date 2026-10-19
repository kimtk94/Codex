"""Synthetic AST-only tests: reflective dispatch counts are not sink proof."""
import unittest
from g12_dynamic_dispatch_audit import inspect_dispatch

class DynamicTests(unittest.TestCase):
    def test_getattr_sheet_method_hint_and_direct_call(self):
        raw=b"def f(contract_ws):\n return getattr(contract_ws, 'update')(x=1)\n"
        out=inspect_dispatch(raw)
        self.assertEqual(out["attribute_target_method_counts"],{"update":1})
        self.assertEqual(out["sheet_name_hint_counts"],{"update":1})
        self.assertEqual(out["direct_getattr_result_invocations"],1)
        self.assertFalse(out["all_dynamic_sheet_sinks_intercepted"])

    def test_same_method_on_dict_is_not_sheets_proof(self):
        raw=b"def f(data):\n return getattr(data,'update')({'x':1})\n"
        out=inspect_dispatch(raw)
        self.assertEqual(out["attribute_target_method_counts"]["update"],1)
        self.assertEqual(out["sheet_name_hint_counts"],{})
        self.assertFalse(out["method_literal_is_actual_sheet_call_proof"])

    def test_unknown_method_name_blocks_exhaustiveness(self):
        raw=b"def f(ws, name):\n return getattr(ws,name)()\n"
        out=inspect_dispatch(raw)
        self.assertEqual(out["dynamic_target_unresolved"],1)
        self.assertEqual(out["attribute_target_method_counts"],
                         {"DYNAMIC_METHOD_ARGUMENT":1})

    def test_eval_and_exec_are_explicit(self):
        raw=b"def f(user):\n exec(user)\n return eval(user)\n"
        out=inspect_dispatch(raw)
        self.assertEqual(out["primitive_counts"],{"eval":1,"exec":1})
        self.assertEqual(out["dynamic_target_unresolved"],2)

    def test_no_private_literals_in_output(self):
        raw=b"def f(obj):\n getattr(obj, 'private.email@example.test')\n"
        result=str(inspect_dispatch(raw))
        self.assertNotIn("private.email@example.test",result)

    def test_getattr_with_non_sheet_method_not_false_positive(self):
        raw=b"def f(ws):\n return getattr(ws,'strip')()\n"
        out=inspect_dispatch(raw)
        self.assertEqual(out["attribute_target_method_counts"],
                         {"OTHER_LITERAL_METHOD":1})
        self.assertEqual(out["sheet_name_hint_counts"],{})

    def test_qualified_attribute_method_not_mistaken_for_builtin(self):
        raw=b"def f(obj):\n obj.getattr('update')\n getattr(obj,'clear')\n"
        out=inspect_dispatch(raw)
        self.assertEqual(out["primitive_counts"],{"getattr":1})
        self.assertEqual(out["qualified_attribute_dispatch_name_counts"],{"getattr":1})
        self.assertEqual(out["broad_dispatch_name_matches"],2)
        self.assertEqual(out["attribute_target_method_counts"],{"clear":1})

    def test_direct_attr_method_calls_not_counted_as_getattr(self):
        raw=b"def f(ws):\n return ws.update(values=[1])\n"
        self.assertEqual(inspect_dispatch(raw)["total_dynamic_primitive_calls"],0)

    def test_setattr_known_method_counts_but_no_proof(self):
        raw=b"def f(worksheet):\n setattr(worksheet,'clear',object())\n"
        out=inspect_dispatch(raw)
        self.assertEqual(out["primitive_counts"],{"setattr":1})
        self.assertEqual(out["attribute_target_method_counts"],{"clear":1})

    def test_nested_reflection_expression_is_ast_only(self):
        raw=b"raise RuntimeError('do not execute')\ndef main():\n return getattr(f(), 'batch_update')\n"
        out=inspect_dispatch(raw)
        self.assertFalse(out["source_imported_or_executed"])
        self.assertFalse(out["release_authorized"])

if __name__=="__main__":
    unittest.main()
