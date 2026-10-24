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
if __name__=="__main__":unittest.main()
