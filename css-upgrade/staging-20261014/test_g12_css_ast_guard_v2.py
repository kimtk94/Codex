"""G12 V2 single-evaluation guard synthetic tests; no production services."""
import unittest
from g12_css_ast_guard_v2 import __g12_guard_sheet_writer__ as fence, guard_ast

class WS:
    def __init__(self,title="TEST OUTPUT",ident=50):
        self.title,self.id,self.writes=title,ident,0
    def clear(self):
        self.writes+=1
        return "ok"
    def update(self,**kwargs):
        self.writes+=1
        return True

def sandbox(source, names):
    code,metrics=guard_ast(source)
    values={"__g12_guard_sheet_writer__":fence}
    values.update(names)
    exec(code,values)
    return values,metrics

class V2Tests(unittest.TestCase):
    def test_function_writer_receiver_evaluated_once(self):
        a=WS(); b=WS("CSS Contract-SIF Tracker",1618938211)
        calls=[]
        def select():
            calls.append(1)
            return [a,b][len(calls)-1]
        def set_with_dataframe(ws,frame):
            ws.clear()
            return True
        ns,metrics=sandbox(
            b"def run():\n    return set_with_dataframe(select(), [1])\n",
            {"select":select,"set_with_dataframe":set_with_dataframe})
        self.assertTrue(ns["run"]())
        self.assertEqual(len(calls),1)
        self.assertEqual((a.writes,b.writes),(1,0))
        self.assertTrue(metrics["expression_receiver_evaluated_once_in_wrapped_sites"])

    def test_method_receiver_evaluated_once_on_safe_object(self):
        a=WS();calls=[]
        def chooser():
            calls.append(1);return a
        ns,info=sandbox(b"def run():\n return sheet.clear()\n",{"sheet":a})
        self.assertEqual(ns["run"](),"ok")
        self.assertEqual(info["known_writer_calls_instrumented"],1)

    def test_protected_tab_blocks_and_skips_payload(self):
        ws=WS("CSS Project Dashboard",948865119);effects=[]
        def payload():
            effects.append("called")
        ns,_=sandbox(b"def run(ws):\n return ws.update(values=payload())\n",
                     {"payload":payload})
        with self.assertRaisesRegex(RuntimeError,"PROTECTED_TAB"):
            ns["run"](ws)
        self.assertEqual(ws.writes,0)
        self.assertEqual(effects,[])

    def test_all_four_tabs_denied(self):
        for title,sid in [
            ("CSS Project Dashboard",948865119),
            ("CSS Contract-SIF Tracker",1618938211),
            ("CSS Contract-SIF Skipped",692581491),
            ("CSS Manual Exclusions",1445506838),
        ]:
            with self.subTest(title=title):
                with self.assertRaisesRegex(RuntimeError,"PROTECTED_TAB"):
                    fence(WS(title,sid),"clear")

    def test_matching_id_other_name_denied(self):
        with self.assertRaisesRegex(RuntimeError,"PROTECTED_TAB"):
            fence(WS("SOME OTHER TAB",1618938211),"clear")

    def test_matching_title_other_id_denied(self):
        with self.assertRaisesRegex(RuntimeError,"PROTECTED_TAB"):
            fence(WS("CSS Contract-SIF Tracker",898989),"clear")

    def test_invalid_identity_denied(self):
        for bad in (None,False,True,"17"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(RuntimeError,"UNKNOWN_WORKSHEET"):
                    fence(WS("NEW OUTPUT",bad),"clear")

    def test_guarded_arg_not_captured(self):
        ws=WS();log=[]
        def set_with_dataframe(target,value):
            log.append(value)
        ns,_=sandbox(
            b"def go(ws):\n __g12_scoped_target_1=71\n return set_with_dataframe(ws,__g12_scoped_target_1)\n",
            {"set_with_dataframe":set_with_dataframe})
        ns["go"](ws)
        self.assertEqual(log,[71])

    def test_compile_does_not_execute_source(self):
        source=b"raise RuntimeError('must not run')\ndef run():\n ws.clear()\n"
        _,report=guard_ast(source)
        self.assertFalse(report["runtime_guard_executed_on_real_css"])

    def test_strict_unclassified_direct_mapping_method_blocks(self):
        with self.assertRaisesRegex(RuntimeError,"UNCLASSIFIED"):
            guard_ast(b"def run(mapping):\n mapping.update({})\n",reject_unclassified=True)

    def test_dynamic_getattr_bypass_is_not_proven_safe(self):
        _,report=guard_ast(b"def run(ws):\n getattr(ws,'clear')()\n")
        self.assertEqual(report["known_writer_calls_instrumented"],0)
        self.assertFalse(report["all_sink_coverage_proven"])

    def test_sha_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"FINGERPRINT_MISMATCH"):
            guard_ast(b"def run():\n pass\n",exact_sha="f"*64)

    def test_unclassified_api_method_breakdown_is_aggregate_only(self):
        raw=b"def main(data):\n data.update({'sensitive@example.test':1})\n data.clear()\n"
        _,report=guard_ast(raw)
        self.assertEqual(report["unknown_method_counts"],{"clear":1,"update":1})
        self.assertEqual(report["unknown_receiver_shapes"],{"Name":2})
        self.assertNotIn("sensitive@example.test",str(report))

    def test_unclassified_path_exposed_without_strict(self):
        _,result=guard_ast(b"def run(data):\n data.update({})\n")
        self.assertEqual(result["unknown_writer_candidates"],1)
        self.assertTrue(result["unknown_sites_require_review"])

    def test_allowed_output_writer_still_works(self):
        ws=WS()
        ns,_=sandbox(b"def go(sheet_ws):\n return sheet_ws.clear()\n",{})
        self.assertEqual(ns["go"](ws),"ok")
        self.assertEqual(ws.writes,1)

    def test_nested_function_writer_receiver_single_eval(self):
        ws=WS();counts=[]
        def choose():
            counts.append(1)
            return ws
        def set_with_dataframe(w,p):
            return w.clear()
        ns,_=sandbox(b"def go():\n return set_with_dataframe(choose(),[1])\n",
                     {"choose":choose,"set_with_dataframe":set_with_dataframe})
        self.assertEqual(ns["go"](),"ok")
        self.assertEqual(len(counts),1)

class TriageTests(unittest.TestCase):
    def test_receiver_literal_and_constructor_hints_only(self):
        from g12_private_v2_compile import triage_local_receivers
        raw=b"""def example():
    data = {}
    data.update({"email": "secret@demo.invalid"})
    rows = []
    rows.sort()
    built = dict()
    built.update({"x": 1})
    uncertain = factory()
    uncertain.update({"x": 1})
"""
        report=triage_local_receivers(raw)
        self.assertEqual(report["update:LOCAL_DICT_LITERAL_HINT"],1)
        self.assertEqual(report["sort:LOCAL_LIST_LITERAL_HINT"],1)
        self.assertEqual(report["update:LOCAL_BUILTIN_CONSTRUCTOR_HINT"],1)
        self.assertEqual(report["update:LOCAL_CALL_ASSIGNMENT_UNRESOLVED"],1)
        self.assertEqual(sum(report.values()),4)
        self.assertNotIn("secret@demo.invalid",str(report))

    def test_unknown_receiver_remains_unknown(self):
        from g12_private_v2_compile import triage_local_receivers
        raw=b"""def example(source):
    source.update({"x": 1})
    source.clear()
"""
        result=triage_local_receivers(raw)
        self.assertEqual(result["update:FUNCTION_PARAMETER_UNRESOLVED"],1)
        self.assertEqual(result["clear:FUNCTION_PARAMETER_UNRESOLVED"],1)

if __name__=="__main__":
    unittest.main()
