import sys
import unittest
sys.path.insert(0,"automation/feishu")
from tax_invoice_forecast_reconcile import reconcile_rows, resolution, mea_from_title, month_overrides

IH=["Invoice No","Year-Month","Revenue KRW (Tax Invoice)","AMEA ID","H Project ID"]
PH=["Contract Number","Contract Name","Sub-Project Number","Staging Number",
    "Forecast Completion Month","Forecast Category","Projected KRW @1500"]

def row(name,stage,category="FORECAST",month="2026-11",amount=100000):
    return ["H123","Korea-Test-AMEA2026101234","X123",stage,month,category,amount]

class ReconcileTests(unittest.TestCase):
    def test_completed_strong_dedup(self):
        i=[IH,["INV1","2026-10",100000,"AMEA2026101234","H123"]]
        p=[PH,row("x","F001","COMPLETED","2026-10")]
        m,r,c=reconcile_rows(i,p,"now")
        self.assertEqual(m[1][1],100000)
        self.assertEqual(m[1][3],0)
        self.assertEqual(m[1][9],1)
    def test_partial_stage_keeps_forecast(self):
        i=[IH,["INV1","2026-10",100000,"AMEA2026101234","H123"]]
        p=[PH,row("x","F002")]
        m,r,c=reconcile_rows(i,p,"now")
        self.assertEqual(m[2][3],100000)
        self.assertEqual(m[2][10],1)
    def test_conflicting_amea_never_dedup(self):
        i=[IH,["INV1","2026-10",100000,"AMEA2026109999","H123"]]
        p=[PH,row("x","F001","COMPLETED","2026-10")]
        m,r,c=reconcile_rows(i,p,"now")
        self.assertEqual(m[1][3],100000)
        self.assertEqual(m[1][9],0)
    def test_duplicate_invoice_id_does_not_double_count(self):
        i=[IH,["INV1","2026-10",100000,"AMEA2026101234","H123"],
              ["INV1","2026-10",100000,"AMEA2026101234","H123"]]
        p=[PH,row("x","F001","COMPLETED","2026-10")]
        m,r,c=reconcile_rows(i,p,"now")
        self.assertEqual(m[1][1],100000)
        self.assertEqual(m[1][7],1)
    def test_completed_later_stage_not_auto_deduped(self):
        i=[IH,["INV1","2026-10",100000,"AMEA2026101234","H123"]]
        p=[PH,row("x","X123-F002","COMPLETED","2026-10")]
        m,r,c=reconcile_rows(i,p,"now")
        self.assertEqual(m[1][3],100000)
        self.assertEqual(m[1][9],0)
    def test_override_moves_project_from_november_to_december(self):
        i=[IH,["INV1","2026-10",100000,"AMEA2026108888","H888"]]
        p=[PH,row("x","F001","FORECAST","2026-11",250000)]
        monthly,reviews,counts,control=reconcile_rows(i,p,"now",{"X123":"2026-12"},with_control=True)
        data={r[0]:r for r in monthly[1:]}
        self.assertEqual(data["2026-12"][3],250000)
        self.assertEqual(control[1][3],"2026-12")
    def test_manual_month_includes_blocked_with_zero_amount(self):
        i=[IH,["INV1","2026-10",100000,"AMEA2026108888","H888"]]
        p=[PH,row("x","F001","EXCLUDED","",0)]
        m,review,counts,control=reconcile_rows(i,p,"now",{"X123":"2026-12"},with_control=True)
        self.assertEqual(m[-1][8],1)
    def test_blank_manual_month_is_not_an_error(self):
        self.assertEqual(month_overrides([["Sub-Project Number","Manual Completion Month (YYYY-MM)"],["X123",None],["X124",""]]),{"X123":"","X124":""})
    def test_invalid_manual_month_rejected(self):
        with self.assertRaisesRegex(RuntimeError,"CONTROL_MONTH_INVALID"):
            month_overrides([["Sub-Project Number","Manual Completion Month (YYYY-MM)"],["X123","2026-13"]])
    def test_mismatched_duplicate_id_fails(self):
        i=[IH,["INV1","2026-10",100000,"AMEA2026101234","H123"],
              ["INV1","2026-10",120000,"AMEA2026101234","H123"]]
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE_INVOICE_CONFLICT"):
            reconcile_rows(i,[PH,row("x","F001")],"now")
    def test_revenue_writer_preserves_dashboard_formula_columns(self):
        import inspect
        from tax_invoice_forecast_reconcile import publish
        source=inspect.getsource(publish)
        self.assertIn("for name in (OUTPUT_TAB,REVIEW_TAB)",source)
        self.assertIn("!A1:N2000",source)
        self.assertIn("!A1:K2000",inspect.getsource(__import__("tax_invoice_forecast_reconcile")).replace("'", ""))
        self.assertNotIn("BI 2026 Forecast Overview",source)
        self.assertNotIn("Unissued Invoice Watch",source)
        self.assertNotIn("Partial Invoice Reconciliation",source)
    def test_publish_runtime_writes_only_approved_ranges(self):
        from unittest.mock import patch
        import tax_invoice_forecast_reconcile as mod
        calls=[]
        def fake_api(session,method,path,**kwargs):
            calls.append((method,path))
            if method=="GET" and path=="?fields=sheets.properties":
                return {"sheets":[]}
            return {"values":[]}
        def fake_values(session,tab,start,rows):
            calls.append(("WRITE",tab,start))
        with patch.object(mod,"read",return_value=[["header"]]), \
             patch.object(mod,"sheet",return_value=None), \
             patch.object(mod,"api",side_effect=fake_api), \
             patch.object(mod,"values",side_effect=fake_values), \
             patch.object(mod,"month_overrides",return_value={}), \
             patch.object(mod,"reconcile_rows",return_value=(
                 [["Month"],["2026-10"]],[["Contract"]],{"DEDUPE_ISSUED_COMPLETED":0},[["Sub-Project Number"]])):
            mod.publish(object())
        writes=[x for x in calls if x[0]=="WRITE"]
        self.assertEqual([(x[1],x[2]) for x in writes],[
            ("BI Revenue Actual Forecast","A1"),
            ("BI Revenue Duplicate Review","A1"),
            ("BI Project Month Control","A1")])
        clear_paths=[x[1] for x in calls if x[0]=="POST" and x[1].endswith(":clear")]
        import urllib.parse
        actual=set(urllib.parse.unquote(x) for x in clear_paths)
        self.assertEqual(actual,{
            "/values/'BI Revenue Actual Forecast'!A1:N2000:clear",
            "/values/'BI Revenue Duplicate Review'!A1:N2000:clear",
            "/values/'BI Project Month Control'!A1:K2000:clear"})
        self.assertFalse(any("BI 2026 Forecast Overview" in str(x) for x in calls))

    def test_publish_blocks_unapproved_dashboard_target(self):
        from unittest.mock import patch
        import tax_invoice_forecast_reconcile as mod
        with patch.object(mod,"OUTPUT_TAB","BI 2026 Forecast Overview"):
            with self.assertRaisesRegex(RuntimeError,"UNSAFE_REVENUE_WRITE_TARGET"):
                mod.publish(object())
if __name__=="__main__":unittest.main()
