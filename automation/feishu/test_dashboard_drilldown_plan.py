import copy
import unittest
import json
from dashboard_drilldown_plan import *

P="AMEA2026000001"
H="H209SC26000001"
ID="209126000001"
ID2="209126000002"
def inv(i=ID,month="2026-10",gross=11000,**kwargs):
    f=f"Tax Invoice-{i}-{H}-PO01-{P}-KRW{gross}.pdf"
    return {**{"invoice_number":i,"amount_krw":str(gross),"project_id":P,"h_project_number":H,
            "po_reference":"PO01","attachment_filename":f,
            "subject":"Notice: Invoice Issued & Statement Confirmed",
            "received_at":month+"-12T10:00:00+09:00","imap_uid":"123",
            "ingest_key":"synthetic","validation_status":"FILENAME_PARSED","extracted_at_utc":"synthetic"},**kwargs}
def sources(month="2026-10",rows=None,count=1,gross=11000,net=10000):
    stamp="2026-10-01 09:00:00 KST"
    return {EXTRACT:rows if rows is not None else [inv(month=month)],
            NET:[{"Month":month,"Issued Invoice Gross KRW (VAT incl)":gross,
                  "Issued Net Revenue KRW (VAT excl)":net,"Issued Invoice Count":count,
                  "Issued Net Revenue kUSD @1500":str(Decimal(net)/1500000),
                  "Verified At KST":stamp,"Evidence State":"INVOICE_FILENAME_VERIFIED_NET"}],
            LIFE:[{"Month":month,"Actual Invoice KRW":gross,"Invoice Count":count}],
            AUTH:[{"Month":month,"Source Tab":tab,"Source Role":role,"Issued Invoice Count":count,
                   "Amount KRW":amount,"Tax Basis":basis,"Source Parity":state,"Authoritative For KPI":"YES",
                   "Verified KST":stamp} for tab,role,amount,basis,state in [
                (NET,"CANONICAL_ISSUED_NET",net,"VAT_EXCLUDED","MATCHED_TO_INVOICE_SOURCE"),
                (LIFE,"CANONICAL_ACTUAL_GROSS",gross,"VAT_INCLUDED","MATCHED_TO_NET_AUDIT")]],
            LEGACY:[]}

class ChartDrilldownTests(unittest.TestCase):
    def test_parity_and_selection_restore(self):
        s=sources(rows=[inv(),inv(ID2)],count=2,gross=22000,net=20000)
        before=copy.deepcopy(s)
        summary,ready=plan(s)
        self.assertEqual(summary["verified_review_members"],2)
        rows=ready["2026-10"]
        self.assertEqual(summary["months"]["2026-10"]["state"],"VERIFIED_PUBLISHED_MONTH_MEMBERS")
        key=rows[0]["Source Key"]
        result=member_totals(rows,[key])
        self.assertEqual(result["original"]["count"],2)
        self.assertEqual(result["selected"]["net_known_krw"],10000)
        self.assertEqual(result["excluded"]["gross_known_krw"],11000)
        self.assertEqual(member_totals(rows)["selected"]["count"],2)
        self.assertEqual(s,before)
        self.assertNotIn(ID,json.dumps(summary))

    def test_mismatch_blocks_entire_month(self):
        summary,ready=plan(sources(rows=[inv(),inv(ID2)]))
        self.assertEqual(summary["months"]["2026-10"]["state"],"SOURCE_MEMBER_PARITY_REVIEW")
        self.assertEqual(ready,{})
        self.assertFalse(summary["months"]["2026-10"]["member_parity"]["count"])

    def test_authority_failure_blocks_even_matching_total(self):
        s=sources()
        s[AUTH][0]["Authoritative For KPI"]="NO"
        summary,ready=plan(s)
        self.assertEqual(summary["months"]["2026-10"]["state"],"AUTHORITY_REVIEW")
        self.assertEqual(ready,{})

    def test_historical_and_nonissued_not_certified(self):
        s=sources(month="2026-09")
        summary,ready=plan(s)
        self.assertEqual(summary["months"]["2026-09"]["state"],"HISTORICAL_MEMBER_AUTHORITY_NOT_ATTESTED")
        self.assertEqual(ready,{})
        s=sources(rows=[inv(subject="Re: Notice: Invoice Issued & Statement Confirmed")])
        summary,ready=plan(s)
        self.assertEqual(ready,{})
        self.assertEqual(summary["extract_unique_members"],0)

    def test_duplicates_and_filename_conflicts(self):
        s=sources(rows=[inv(),inv()])
        summary,ready=plan(s)
        self.assertEqual(summary["verified_review_members"],1)
        self.assertEqual(summary["extract_exclusions"],{"REPEATED_IDENTICAL_MEMBER":1})
        with self.assertRaisesRegex(DrilldownError,"DUPLICATE_MEMBER_CONFLICT"):
            plan(sources(rows=[inv(),inv(gross=22000)]))
        with self.assertRaisesRegex(DrilldownError,"AMOUNT_UID_MISMATCH"):
            plan(sources(rows=[inv(amount_krw="12000")]))

    def test_unknown_amount_and_invalid_exclusion(self):
        r=[{"Source Key":"A","Gross KRW":None,"Net KRW":None}]
        out=member_totals(r)
        self.assertEqual(out["selected"]["net_unknown_count"],1)
        self.assertEqual(out["selected"]["count"],1)
        with self.assertRaisesRegex(DrilldownError,"EXCLUSION_OUTSIDE_MEMBERSHIP"):
            member_totals(r,["B"])
        with self.assertRaisesRegex(DrilldownError,"KEY_INVALID_OR_DUPLICATE"):
            member_totals(r+r)

    def test_native_config_preserves_operational_filters(self):
        cfg={"table_name":"Project Progress Board","count_all":True,
             "filter":{"conjunction":"and","conditions":[
                 {"field_name":"Payment Owner Scope","operator":"is","value":"MY_VERIFIED"}]}}
        before=copy.deepcopy(cfg)
        out=analysis_config(cfg)
        self.assertEqual(cfg,before)
        self.assertEqual(out["filter"]["conditions"][:-1],cfg["filter"]["conditions"])
        self.assertEqual(out["filter"]["conditions"][-1]["value"],False)
        self.assertEqual(review_chart_config()["filter"]["conditions"][-1]["field_name"],EXCLUDE)
        self.assertEqual(len(review_chart_config(filtered=False)["filter"]["conditions"]),1)
        with self.assertRaisesRegex(DrilldownError,"NOT_PROJECT_MEMBER_SOURCE"):
            analysis_config({"table_name":"Monthly Tax Invoice"})

    def test_receipt_month_uses_kst_and_unzoned_fails(self):
        self.assertEqual(issue_month("2026-10-31T16:00:00Z"),"2026-11")
        with self.assertRaisesRegex(DrilldownError,"UNZONED"):
            issue_month("2026-10-31T16:00:00")

if __name__=="__main__":
    unittest.main()
