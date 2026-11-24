import re
import unittest
from datetime import date,datetime,timezone,timedelta
from unittest.mock import patch
import nba_refresh_pool as target


def sources():
    stamp=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")
    personal=[["Lead ID","Created Date","Email","My Mail Status","Description Class",
               "Description","Lead Status","Opportunity ID","Latest QQ Outbound Checked"]]
    recent=["2026-10-25","PRESENT","RNA-seq quote"]
    latest=[["SFDC Lead ID"]]
    for i in range(450):
        state="NO_PERSONAL_OUTBOUND_EVIDENCE" if i==1 else "SENT_AFTER_LEAD_CONFIRMED"
        personal.append([f"Lead-{i}","2026-10-25",f"lead{i}@example.com",state,
                        "PRESENT","RNA-seq quote","New","",stamp])
        latest.append([f"Lead-{i}"])
    return {
        "BI Followup Unified":[["Priority","Source","Record ID","Original Status"],
                               ["P0","CSS","ACT-1","미검토"]],
        "Lead My Sent Audit":personal,
        "SFDC Email Leads Raw":latest,
        "BI Unanswered Triage":[["Thread UID","Aging Days","Effective Queue"],
                                ["inbox:1","3","REVIEW_2D"]],
        "NBA Decision Checkboxes":[["Source","Record ID","완료 체크"]],
        "Lead Decision Ledger":[["Lead ID","Decision"]],
        "Automation Health":[["Source","Updated","State","Details"],
                             ["Lead My Sent Audit","2026-10-29 22:59 KST","PASS_VERIFIED",
                              "leads=450 after=449 prior_only=0 never=1"]],
    }


class FakeValues:
    def __init__(self, data):
        self.sources=data
        self.writes=[]
        self.read_ranges=[]
    def get(self, spreadsheetId,range,valueRenderOption):
        class Request:
            def __init__(self,value):self.value=value
            def execute(self):return {"values":self.value}
        self.read_ranges.append(range)
        name=range.split("'!")[0][1:]
        match=re.search(r"(\d+)$", range)
        if not match:
            raise AssertionError("Missing synthetic bounded range")
        return Request(self.sources[name][:int(match.group(1))])
    def batchUpdate(self,**kwargs):
        self.writes.append(("batchUpdate",kwargs))
        raise AssertionError("No writing expected")


class FakeAPI:
    def __init__(self,values,capacity=2000):
        self.reader=values
        self.capacity=capacity
    def values(self):return self.reader
    def get(self,**kwargs):
        class Request:
            def __init__(self,capacity,data):
                self.capacity=capacity
                self.data=data
            def execute(self):
                return {"sheets":[{"properties":{"title":tab,
                    "gridProperties":{"rowCount":len(rows)}}}
                    for tab,rows in self.data.items() if tab!="NBA Action Pool"] +
                    [{"properties":{"title":"NBA Action Pool",
                     "gridProperties":{"rowCount":self.capacity}}}]}
        return Request(self.capacity,self.reader.sources)


class LiveDryRunTests(unittest.TestCase):
    def test_read_all_sources_without_mutation(self):
        v=FakeValues(sources())
        api=FakeAPI(v)
        with patch.object(target,"date") as mockdate:
            mockdate.today.return_value=date(2026,10,29)
            self.assertEqual(target.sync(api,dry_run=True),3)
        self.assertEqual(v.writes,[])

    def test_overflow_refuses_write(self):
        v=FakeValues(sources())
        with self.assertRaisesRegex(ValueError,"exceeds pool capacity"):
            target.sync(FakeAPI(v,capacity=1),dry_run=False)
        self.assertEqual(v.writes,[])

    def test_prior_completed_id_is_suppressed(self):
        vals=sources()
        vals["NBA Decision Checkboxes"].append(["LEAD","Lead-1",True])
        v=FakeValues(vals)
        self.assertEqual(target.sync(FakeAPI(v),dry_run=True),2)
        self.assertEqual(v.writes,[])

    def test_stale_personal_sheet_blocks_write(self):
        vals=sources()
        vals["Automation Health"][1][2]="MANUAL_VERIFIED"
        v=FakeValues(vals)
        with self.assertRaisesRegex(ValueError,"not verified"):
            target.sync(FakeAPI(v),dry_run=False)
        self.assertEqual(v.writes,[])

    def test_more_than_one_thousand_leads_are_all_read_without_truncation(self):
        vals=sources()
        stamp=vals["Lead My Sent Audit"][1][-1]
        for i in range(450,1053):
            vals["Lead My Sent Audit"].append(
                [f"Lead-{i}","2026-11-20",f"lead{i}@example.com",
                 "SENT_AFTER_LEAD_CONFIRMED","PRESENT","RNA","New","",stamp])
            vals["SFDC Email Leads Raw"].append([f"Lead-{i}"])
        v=FakeValues(vals)
        with patch.object(target,"date") as mockdate:
            mockdate.today.return_value=date(2026,11,23)
            self.assertEqual(target.sync(FakeAPI(v),dry_run=True),3)
        self.assertIn("'Lead My Sent Audit'!A1:T1054",v.read_ranges)
        self.assertIn("'SFDC Email Leads Raw'!A1:W1054",v.read_ranges)
        self.assertEqual(v.writes,[])

    def test_unverified_grid_cannot_silently_truncate_lead_source(self):
        with self.assertRaisesRegex(ValueError,"NBA_SOURCE_TAB_MISSING_OR_AMBIGUOUS"):
            target.source_rows({"sheets":[]},"Lead My Sent Audit")
        huge={"sheets":[{"properties":{"title":"Lead My Sent Audit",
            "gridProperties":{"rowCount":10001}}}]}
        with self.assertRaisesRegex(ValueError,"NBA_SOURCE_GRID_SIZE_UNVERIFIED"):
            target.source_rows(huge,"Lead My Sent Audit")

    def test_report_mismatch_blocks_write(self):
        vals=sources()
        vals["SFDC Email Leads Raw"].pop()
        v=FakeValues(vals)
        with self.assertRaisesRegex(ValueError,"do not match"):
            target.sync(FakeAPI(v),dry_run=False)
        self.assertEqual(v.writes,[])


if __name__=="__main__":
    unittest.main()
