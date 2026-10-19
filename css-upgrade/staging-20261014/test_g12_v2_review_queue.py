"""G12 55-site queue synthetic regression; no production CSS or external writes."""
import unittest
from g12_v2_review_queue import build_queue
from g12_css_ast_guard_v2 import guard_ast


class ReviewQueueTests(unittest.TestCase):
    def test_structural_clear_and_sort_review_before_update(self):
        src=b"def f(rows,cache):\n cache.update({'x':1})\n rows.sort()\n rows.clear()\n"
        result=build_queue(src)
        self.assertEqual(result["candidate_count"],3)
        self.assertEqual([x["method"] for x in result["review_queue"]],["sort","clear","update"])
        self.assertTrue(all(not x["safe_to_ignore"] for x in result["review_queue"]))

    def test_indirect_call_result_ranked_p0(self):
        src=b"def f():\n get_target().update({'x':1})\n"
        item=build_queue(src)["review_queue"][0]
        self.assertEqual(item["receiver_shape"],"Call")
        self.assertEqual(item["priority"],"P0_INDIRECT_RECEIVER_REVIEW")

    def test_subscript_receiver_ranked_p0(self):
        src=b"def f(items):\n items[0].update({'x':1})\n"
        item=build_queue(src)["review_queue"][0]
        self.assertEqual(item["receiver_shape"],"Subscript")
        self.assertEqual(item["priority"],"P0_INDIRECT_RECEIVER_REVIEW")

    def test_local_dict_hint_is_not_whitelisted(self):
        src=b"def f():\n data={}\n data.update({'private@example.org':1})\n"
        item=build_queue(src)["review_queue"][0]
        self.assertEqual(item["provenance"],"SINGLE_BINDING_CONTAINER_LITERAL_HINT")
        self.assertEqual(item["priority"],"P2_UNVERIFIED_CONTAINER_OR_OTHER")
        self.assertFalse(item["destination_proven"])
        self.assertNotIn("private@example.org",str(build_queue(src)))

    def test_rebinding_in_conditional_stays_ambiguous(self):
        src=b"def f(flag):\n data={}\n if flag: data = get_x()\n data.update({'x':1})\n"
        item=build_queue(src)["review_queue"][0]
        self.assertEqual(item["provenance"],"MULTIPLE_BINDINGS_OR_REASSIGNMENT")
        self.assertEqual(item["priority"],"P1_AMBIGUOUS_BINDING_REVIEW")

    def test_nested_functions_count_once(self):
        src=b"def outer():\n def inner(rows):\n  rows.sort()\n"
        result=build_queue(src)
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["review_queue"][0]["scope"],"helper")

    def test_protected_sheet_tokens_are_not_unknown(self):
        src=b"def f(contract_ws,rows):\n contract_ws.clear()\n rows.sort()\n"
        result=build_queue(src)
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["review_queue"][0]["method"],"sort")

    def test_occurrence_index_for_same_line_calls(self):
        src=b"def f(a,b):\n a.update({}); b.update({})\n"
        result=build_queue(src)
        self.assertEqual(result["candidate_count"],2)
        self.assertEqual([x["occurrence"] for x in result["review_queue"]],[1,2])

    def test_unclassified_count_matches_v2(self):
        src=b"def f(rows,ws,d):\n rows.sort()\n ws.update(values=[1])\n d.clear()\n"
        _,summary=guard_ast(src)
        queue=build_queue(src)
        self.assertEqual(queue["candidate_count"],summary["unknown_writer_candidates"])
        self.assertEqual(queue["counts_by_method"],summary["unknown_method_counts"])
        self.assertEqual(queue["counts_by_shape"],summary["unknown_receiver_shapes"])

    def test_compile_only_never_runs_source(self):
        src=b"raise RuntimeError('MUST NOT RUN')\ndef f(a):\n a.clear()\n"
        result=build_queue(src)
        self.assertFalse(result["source_executed"])
        self.assertFalse(result["release_authorized"])

    def test_metadata_contains_no_raw_receiver_name(self):
        src=b"def f(customer_token):\n customer_token.update({'customer@example.org':1})\n"
        result=str(build_queue(src))
        self.assertNotIn("customer_token",result)
        self.assertNotIn("customer@example.org",result)

    def test_no_automatic_allowlist(self):
        src=b"def f():\n data={}\n data.update({'x':1})\n"
        result=build_queue(src)
        self.assertEqual(result["automatic_allowlist_count"],0)
        self.assertFalse(result["write_destination_proven"])


if __name__=="__main__":
    unittest.main()
