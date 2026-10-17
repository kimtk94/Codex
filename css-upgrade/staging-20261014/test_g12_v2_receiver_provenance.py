"""Synthetic-only regression for aggregate G12 receiver provenance hints."""
import unittest
from g12_v2_receiver_provenance import audit_receiver_provenance as inspect

class ProvenanceTests(unittest.TestCase):
    def test_single_container_literal(self):
        result=inspect(b"def f():\n data={}\n data.update({'private@example.test':1})\n")
        self.assertEqual(result["provenance_hint_counts"],{
            "SINGLE_BINDING_CONTAINER_LITERAL_HINT":1})
        self.assertNotIn("private@example.test",str(result))
        self.assertFalse(result["runtime_type_proven"])

    def test_rebinding_refuses_container_claim(self):
        result=inspect(b"def f():\n data={}\n data=external()\n data.update({'x':1})\n")
        self.assertEqual(result["provenance_hint_counts"],{
            "MULTIPLE_BINDINGS_OR_REASSIGNMENT":1})

    def test_augmented_assignment_refuses_single_binding(self):
        result=inspect(b"def f():\n data=[]\n data += [1]\n data.sort()\n")
        self.assertEqual(result["provenance_hint_counts"],{
            "MULTIPLE_BINDINGS_OR_REASSIGNMENT":1})

    def test_branch_assignment_is_not_guaranteed(self):
        result=inspect(b"def f(flag):\n if flag:\n  data=[]\n data.sort()\n")
        self.assertEqual(result["provenance_hint_counts"],{
            "NESTED_OR_COMPLEX_BINDING":1})

    def test_parameter_unresolved(self):
        result=inspect(b"def f(data):\n data.update({'x':1})\n")
        self.assertEqual(result["provenance_hint_counts"],{
            "PARAMETER_UNRESOLVED":1})

    def test_shadowable_builtin_constructor_only_hint(self):
        result=inspect(b"def f():\n data=dict()\n data.update({'x':1})\n")
        self.assertEqual(result["provenance_hint_counts"],{
            "SINGLE_BINDING_BUILTIN_NAME_CONSTRUCTOR_HINT":1})
        self.assertEqual(result["confirmed_non_sheet_sinks"],0)

    def test_unknown_factory_remains_unknown(self):
        result=inspect(b"def f():\n data=some_factory()\n data.update({'x':1})\n")
        self.assertEqual(result["provenance_hint_counts"],{
            "SINGLE_BINDING_CALL_RESULT_UNKNOWN":1})

    def test_sheet_like_name_excluded_from_uncategorized_set(self):
        result=inspect(b"def f():\n contract_ws.clear()\n rows.sort()\n news.update({'x':1})\n")
        self.assertEqual(result["unclassified_site_count"],2)
        self.assertEqual(result["method_counts"],{"sort":1,"update":1})

    def test_nested_function_and_class_are_scoped_once(self):
        result=inspect(b"class C:\n def f(self,items):\n  items.sort()\ndef outer():\n def nested(x):\n  x.clear()\n")
        self.assertEqual(result["unclassified_site_count"],2)
        self.assertEqual(result["provenance_hint_counts"],{
            "PARAMETER_UNRESOLVED":2})

    def test_nonlocal_call_result_not_assumed_safe(self):
        result=inspect(b"def f():\n data=make()\n data.clear()\n")
        self.assertFalse(result["release_authorized"])
        self.assertEqual(result["confirmed_sheet_sinks"],0)

if __name__=="__main__":
    unittest.main()
