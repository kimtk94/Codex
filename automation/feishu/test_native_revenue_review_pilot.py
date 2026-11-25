import copy
import json
import unittest
from native_revenue_review_pilot import *
from test_dashboard_drilldown_plan import sources,inv

def fixture():
    return sources(rows=[inv("209126"+str(i+1).zfill(6)) for i in range(EXPECTED_COUNT)],
                   count=EXPECTED_COUNT,gross=11000*EXPECTED_COUNT,net=10000*EXPECTED_COUNT)

class Fake:
    def __init__(self,source):
        self.ts={OFFICIAL_ID:OFFICIAL,"tblOriginal":"Unrelated source"}
        self.ds={"blkOriginal":"Existing Dashboard"}
        self.rows={OFFICIAL_ID:[{"record_id":"recOfficial","fields":snapshot(source)["official"]}]}
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
        self.assertEqual(result["members"],48)
        self.assertEqual(result["review_digest"],self.digest)
        self.assertEqual(self.b.writes,[])
        self.assertNotIn("209126000001",json.dumps(result))

    def test_creation_and_existing_check_preserve_manual(self):
        original=copy.deepcopy(self.b.rows[OFFICIAL_ID])
        out=reconcile(self.s,self.b,"apply",self.digest)
        self.assertEqual(out["state"],"CREATED_FROZEN_REVIEW_PILOT")
        self.assertEqual(len(self.b.rows["tblReview"]),48)
        self.assertEqual(len(self.b.charts),5)
        self.assertEqual(self.b.rows[OFFICIAL_ID],original)
        self.assertEqual(self.b.ts["tblOriginal"],"Unrelated source")
        self.b.rows["tblReview"][0]["fields"][EXCLUDE]=True
        self.b.rows["tblReview"][0]["fields"]["제외 사유"]="manual"
        before=copy.deepcopy(self.b.rows)
        writes=list(self.b.writes)
        out=reconcile(self.s,self.b,"apply",self.digest)
        self.assertEqual(out["state"],"EXISTING_SNAPSHOT_VERIFIED_NO_WRITES")
        self.assertEqual(out["selected"],47)
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

    def test_charts_are_exact_month_and_selection_scope(self):
        c=specs(snapshot(self.s)["stamp"])
        for chart in c[1:]:
            cfg=chart["data_config"]
            self.assertEqual(cfg["table_name"],REVIEW)
            self.assertIn({"field_name":"Month","operator":"is","value":MONTH},cfg["filter"]["conditions"])
            self.assertEqual(any(x["field_name"]==EXCLUDE for x in cfg["filter"]["conditions"]),
                             chart["name"].endswith("분석 합계"))

if __name__=="__main__":
    unittest.main()
