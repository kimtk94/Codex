import copy
import json
import unittest
from native_revenue_review_pilot import *
from test_dashboard_drilldown_plan import sources,inv

def fixture():
    out={}
    offset=0
    for month,count in EXPECTED_COUNTS.items():
        s=sources(month=month,rows=[inv("209126"+str(offset+i+1).zfill(6),month=month)
                                    for i in range(count)],
                  count=count,gross=11000*count,net=10000*count)
        for tab in ("BI Revenue Net VAT Monthly","Revenue Source Authority"):
            for r in s[tab]:
                field="Verified At KST" if tab=="BI Revenue Net VAT Monthly" else "Verified KST"
                r[field]=month+"-15 09:00:00 KST"
        s["BI Revenue Lifecycle Monthly"][0]["Snapshot KST"]=month+"-15 09:00:00 KST"
        for tab,rows in s.items():
            out.setdefault(tab,[]).extend(rows)
        offset+=count
    return out

class Fake:
    def __init__(self,source):
        self.ts={OFFICIAL_ID:OFFICIAL,"tblOriginal":"Unrelated source"}
        self.ds={"blkOriginal":"Existing Dashboard"}
        official=snapshot(source)["official"]
        self.rows={OFFICIAL_ID:[{"record_id":"recOfficial"+str(i),"fields":official[m]}
                               for i,m in enumerate(MONTHS)]}
        self.charts={}
        self.writes=[]
    def tables(self):return dict(self.ts)
    def pages(self):return dict(self.ds)
    def records(self,t):return copy.deepcopy(self.rows[t])
    def fields(self,t):
        return [{"field_name":k,"field_id":"fld"+str(i),"type":v,"is_primary":k=="Invoice No"}
                for i,(k,v) in enumerate(REVIEW_FIELDS.items())]
    def create_table(self):
        self.writes.append("table")
        self.ts["tblReview"]=REVIEW;self.rows["tblReview"]=[]
        return "tblReview"
    def create_members(self,t,rows):
        self.writes.append("members")
        for r in rows:
            self.rows[t].append({"record_id":"recMember"+str(len(self.rows[t])),"fields":copy.deepcopy(r)})
    def create_page(self):
        self.writes.append("page");self.ds["blkReview"]=TITLE
        return "blkReview"
    def create_block(self,p,c):
        self.writes.append("block");self.charts[c["name"]]=copy.deepcopy(c)
    def verify_page(self,p,charts):
        if self.charts!={c["name"]:c for c in charts}:fail("FAKE_CHART_DRIFT")

class PilotTests(unittest.TestCase):
    def setUp(self):
        self.s=fixture();self.b=Fake(self.s);self.digest=snapshot(self.s)["digest"]

    def test_plan_matches_official_and_never_writes(self):
        result=reconcile(self.s,self.b)
        self.assertEqual(result["state"],"READY_NEW_REVIEW_PILOT")
        self.assertEqual(result["members"],90)
        self.assertEqual(result["expected_members_by_month"],{"2026-10":48,"2026-11":42})
        self.assertEqual(result["review_digest"],self.digest)
        self.assertEqual(self.b.writes,[])
        self.assertNotIn("209126000001",json.dumps(result))

    def test_creation_and_existing_check_preserve_manual(self):
        original=copy.deepcopy(self.b.rows[OFFICIAL_ID])
        out=reconcile(self.s,self.b,"apply",self.digest)
        self.assertEqual(out["state"],"CREATED_FROZEN_REVIEW_PILOT")
        self.assertEqual(len(self.b.rows["tblReview"]),90)
        self.assertEqual(len(self.b.charts),5)
        self.assertEqual(self.b.rows[OFFICIAL_ID],original)
        self.assertEqual(self.b.ts["tblOriginal"],"Unrelated source")
        self.b.rows["tblReview"][0]["fields"][EXCLUDE]=True
        self.b.rows["tblReview"][0]["fields"]["제외 사유"]="manual"
        before=copy.deepcopy(self.b.rows)
        writes=list(self.b.writes)
        out=reconcile(self.s,self.b,"apply",self.digest)
        self.assertEqual(out["state"],"EXISTING_SNAPSHOT_VERIFIED_NO_WRITES")
        self.assertEqual(out["selected"],89)
        self.assertEqual(out["selection_by_month"],{
            "2026-10":{"original":48,"excluded":1,"selected":47},
            "2026-11":{"original":42,"excluded":0,"selected":42}})
        self.assertEqual(self.b.rows,before)
        self.assertEqual(self.b.writes,writes)

    def test_missing_or_wrong_digest_never_creates(self):
        for d in ("","0"*64):
            with self.assertRaises(DrilldownError):
                reconcile(self.s,self.b,"apply",d)
        self.assertEqual(self.b.writes,[])

    def test_official_mismatch_blocks(self):
        self.b.rows[OFFICIAL_ID][0]["fields"]["Invoice Count"]=47
        with self.assertRaisesRegex(DrilldownError,"OFFICIAL_CHART_TOTAL_MISMATCH"):
            reconcile(self.s,self.b,"apply",self.digest)
        self.assertFalse(self.b.writes)

    def test_partial_target_or_ambiguous_name_blocks(self):
        self.b.ts["tblReview"]=REVIEW
        with self.assertRaisesRegex(DrilldownError,"PARTIAL_TARGET"):
            reconcile(self.s,self.b,"apply",self.digest)
        self.b.ts["tblDuplicate"]=REVIEW
        with self.assertRaisesRegex(DrilldownError,"TARGET_NAME_AMBIGUOUS"):
            reconcile(self.s,self.b)
        self.assertFalse(self.b.writes)

    def test_member_incomplete_no_dashboard_created(self):
        def incomplete(t,rows):
            self.b.rows[t].extend({"record_id":"recMember"+str(i),
                "fields":r} for i,r in enumerate(rows[:-1],len(self.b.rows[t])))
        self.b.create_members=incomplete
        with self.assertRaisesRegex(DrilldownError,"REVIEW_MEMBER_SET_INCOMPLETE"):
            reconcile(self.s,self.b,"apply",self.digest)
        self.assertNotIn(TITLE,self.b.ds.values())

    def test_partial_table_plan_counts_verified_rows_without_writes(self):
        t=self.b.create_table()
        row=snapshot(self.s)["rows"][0]
        self.b.create_members(t,[{**row,EXCLUDE:True,"제외 사유":"private reason"}])
        self.b.rows[t].append({"record_id":"recBlank","fields":{}})
        before=copy.deepcopy(self.b.rows)
        writes=list(self.b.writes)
        out=reconcile(self.s,self.b)
        self.assertEqual(out["state"],"PARTIAL_TARGET_REQUIRES_REVIEW")
        self.assertEqual((out["observed_members"],out["missing_members"]),(1,89))
        self.assertEqual(out["observed_by_month"],{"2026-10":1,"2026-11":0})
        self.assertEqual(out["blank_nonmember_rows"],1)
        self.assertNotIn("private reason",json.dumps(out))
        self.assertEqual(self.b.rows,before)
        self.assertEqual(self.b.writes,writes)
        self.b.rows[t][0]["fields"]["Net KRW"]+=1
        with self.assertRaises(DrilldownError):
            reconcile(self.s,self.b)

    def test_partial_page_plan_reports_unknown_members(self):
        self.b.ds["blkReview"]=TITLE
        out=reconcile(self.s,self.b)
        self.assertIsNone(out["observed_members"])
        self.assertEqual(out["target_dashboard"],"blkReview")
        self.assertEqual(self.b.writes,[])

    def test_only_explicit_empty_records_page_can_omit_items(self):
        path=ROOT+"/tables/tblReview/records"
        def listing(responses, resource=path):
            pages=iter(responses)
            backend=NativeBackend(None,ROOT,lambda *a,**kw:next(pages),None)
            return backend.listing(resource)
        empty={"has_more":False,"total":0}
        self.assertEqual(listing([empty]),[])
        for bad in ({},{"has_more":False},{**empty,"items":None},{**empty,"total":False},
                    {**empty,"total":2},{**empty,"page_token":"more"},{**empty,"has_more":True}):
            with self.subTest(bad=bad), self.assertRaisesRegex(DrilldownError,"INCOMPLETE_LIST"):
                listing([bad])
        with self.assertRaisesRegex(DrilldownError,"INCOMPLETE_LIST"):
            listing([empty],ROOT+"/tables")
        with self.assertRaisesRegex(DrilldownError,"INCOMPLETE_LIST"):
            listing([{"has_more":True,"items":[{}],"page_token":"next"},empty])

    def test_charts_are_month_grouped_and_selection_scoped(self):
        c=specs(snapshot(self.s)["stamps"])
        for chart in c[1:]:
            cfg=chart["data_config"]
            self.assertEqual(cfg["table_name"],REVIEW)
            self.assertEqual(cfg["group_by"][0]["field_name"],"Month")
            self.assertIn({"field_name":"Membership State","operator":"is","value":INCLUSION},
                          cfg["filter"]["conditions"])
            self.assertEqual(any(x["field_name"]==EXCLUDE for x in cfg["filter"]["conditions"]),
                             chart["name"].endswith("분석 합계"))

    def test_november_source_mismatch_blocks_both_months(self):
        self.s["CSS Tax Invoice Extract"].pop()
        with self.assertRaisesRegex(DrilldownError,"SOURCE_MONTH_NOT_READY:2026-11"):
            reconcile(self.s,self.b,"apply",self.digest)
        self.assertFalse(self.b.writes)

    def test_november_authority_missing_blocks(self):
        self.s["Revenue Source Authority"]=[
            r for r in self.s["Revenue Source Authority"] if r["Month"]!="2026-11"]
        with self.assertRaisesRegex(DrilldownError,"SOURCE_MONTH_NOT_READY:2026-11"):
            reconcile(self.s,self.b)
        self.assertFalse(self.b.writes)

    def test_november_official_mismatch_blocks_both_months(self):
        self.b.rows[OFFICIAL_ID][1]["fields"]["Invoice Count"]=37
        with self.assertRaisesRegex(DrilldownError,"OFFICIAL_CHART_TOTAL_MISMATCH:2026-11"):
            reconcile(self.s,self.b,"apply",self.digest)
        self.assertFalse(self.b.writes)

    def test_reviewed_count_change_requires_new_approval(self):
        count=43
        nov=sources(month="2026-11",
                    rows=[inv("209126"+str(49+i).zfill(6),month="2026-11") for i in range(count)],
                    count=count,gross=11000*count,net=10000*count)
        for tab,rows in nov.items():
            if tab=="CSS Tax Invoice Extract":
                self.s[tab]=self.s[tab][:48]+rows
            elif tab!="Revenue Invoice Base":
                self.s[tab]=[r for r in self.s[tab] if r["Month"]!="2026-11"]+rows
        with self.assertRaisesRegex(DrilldownError,"EXPECTED_MEMBER_COUNT_CHANGED:2026-11"):
            reconcile(self.s,self.b)
        self.assertFalse(self.b.writes)

    def test_previous_40_member_november_snapshot_cannot_be_adopted(self):
        count=40
        nov=sources(month="2026-11",
                    rows=[inv("209126"+str(49+i).zfill(6),month="2026-11") for i in range(count)],
                    count=count,gross=11000*count,net=10000*count)
        for tab,rows in nov.items():
            if tab=="CSS Tax Invoice Extract":
                self.s[tab]=self.s[tab][:48]+rows
            elif tab!="Revenue Invoice Base":
                self.s[tab]=[r for r in self.s[tab] if r["Month"]!="2026-11"]+rows
        with self.assertRaisesRegex(DrilldownError,"EXPECTED_MEMBER_COUNT_CHANGED:2026-11"):
            reconcile(self.s,self.b)
        self.assertFalse(self.b.writes)

    def test_legacy_october_dashboard_is_not_reused(self):
        self.b.ds["blkLegacy"]=LEGACY_TITLE
        with self.assertRaisesRegex(DrilldownError,"LEGACY_OCTOBER_PILOT_REQUIRES_REVIEW"):
            reconcile(self.s,self.b,"apply",self.digest)
        self.assertFalse(self.b.writes)

    def test_november_exclusion_and_restore_independent(self):
        reconcile(self.s,self.b,"apply",self.digest)
        row=next(r for r in self.b.rows["tblReview"] if r["fields"]["Month"]=="2026-11")
        row["fields"][EXCLUDE]=True
        out=reconcile(self.s,self.b)
        self.assertEqual(out["selection_by_month"]["2026-10"]["selected"],48)
        self.assertEqual(out["selection_by_month"]["2026-11"]["selected"],41)
        row["fields"][EXCLUDE]=False
        self.assertEqual(reconcile(self.s,self.b)["selected"],90)

if __name__=="__main__":
    unittest.main()
