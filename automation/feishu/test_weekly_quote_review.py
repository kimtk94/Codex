#!/usr/bin/env python3
import unittest
from unittest import mock
import weekly_quote_review as q
from qq_mail_ingest import SafeError

A="a0P"+"A"*12
B="a0P"+"B"*12
C="a0P"+"C"*12
NOW=q.dt.datetime(2026,11,7,16,0,tzinfo=q.KST)

def source():
    return {"Quote Approval Dedup":[
        {"SFDC Record ID":A,"Approval KST":"2026-11-05 10:00:00",
         "Quotation Name":"Active A","Quote Status":"ACTIVE","Approved AND Active":"YES"},
        {"SFDC Record ID":B,"Approval KST":"2026-11-05 11:00:00",
         "Quotation Name":"Inactive B","Quote Status":"INACTIVE","Approved AND Active":"NO"},
        {"SFDC Record ID":C,"Approval KST":"2026-11-05 12:00:00",
         "Quotation Name":"Unknown C","Quote Status":"UNKNOWN","Approved AND Active":"UNVERIFIED"},
    ],"SFDC Quote Export":[
        {"Salesforce Record ID":A+"XYZ","IsActive":"1",
         "Exported At KST":"2026-11-07 12:00:08 KST"},
        {"Salesforce Record ID":B+"XYZ","IsActive":"0",
         "Exported At KST":"2026-11-07 12:00:08 KST"},
    ]}

class PolicyTests(unittest.TestCase):
    def test_status_and_manual_checkbox(self):
        rows=q.review_rows(source(),now=NOW)
        by_id={r["SFDC Record ID"]:r for r in rows}
        self.assertEqual(len(rows),3)
        self.assertEqual(by_id[A]["합산 상태"],q.INCLUDED)
        self.assertEqual(by_id[B]["제외 이유"],"NOT_ACTIVE")
        self.assertEqual(by_id[C]["제외 이유"],"ACTIVE_NOT_VERIFIED")
        approved,include=q.membership(rows)
        self.assertEqual(len(approved["2026-10-30"]),3)
        self.assertEqual(include["2026-10-30"],{A})
        checked=q.review_rows(source(),{"QUOTE_REVIEW:"+A:True},now=NOW)
        a=next(r for r in checked if r["SFDC Record ID"]==A)
        self.assertEqual(a["제외 이유"],"MANUAL_EXCLUDED")
        self.assertEqual(len(q.membership(checked)[1]["2026-10-30"]),0)

    def test_conflicting_active_sources_fail_closed(self):
        data=source()
        data["SFDC Quote Export"][0]["IsActive"]="0"
        r=q.review_rows(data,now=NOW)[0]
        self.assertEqual(r["합산 상태"],q.NOT_INCLUDED)
        data=source()
        data["SFDC Quote Export"]=data["SFDC Quote Export"][1:]
        self.assertEqual(q.review_rows(data,now=NOW)[0]["제외 이유"],"ACTIVE_NOT_VERIFIED")

    def test_duplicate_ids_fail_closed(self):
        data=source()
        data["Quote Approval Dedup"].append(dict(data["Quote Approval Dedup"][0]))
        with self.assertRaisesRegex(SafeError,"DUPLICATE_APPROVAL_ID"):
            q.review_rows(data,now=NOW)

    def test_checkbox_readback_and_untouched_user_field(self):
        row=q.review_rows(source(),now=NOW)[0]
        old={**row,"합산 상태":"NOT_INCLUDED","제외 이유":"MANUAL_EXCLUDED",
             "합산 제외":True}
        record={"record_id":"recOld","fields":old}
        after={"record_id":"recOld","fields":{**row,"합산 제외":True}}
        with mock.patch.object(q,"list_all",return_value=[after]),\
             mock.patch.object(q,"api",return_value={"records":[{}]}) as api:
            result=q.sync_review("tok","/t",[row],[record],"now")
        self.assertTrue(result[row["Source Key"]])
        writes=api.call_args.kwargs["data"]["records"][0]["fields"]
        self.assertNotIn(q.CHECKBOX,writes)
        self.assertEqual(writes["합산 상태"],"INCLUDED")

    def test_fresh_authenticated_quotation_active_proves_four_without_old_export(self):
        records=[]
        quotes=[]
        for i in range(4):
            sid="a0P"+str(i)*12
            qid="QID-2026-11-09-41286"+str(i)
            records.append({"SFDC Record ID":sid,"Quotation Name":qid,
                "Approval KST":"2026-11-09 18:00:00",
                "Quote Status":"UNKNOWN","Approved AND Active":"UNVERIFIED"})
            quotes.extend([{"SFDC Quotation ID":qid,"Active":"1"},
                           {"SFDC Quotation ID":qid,"Active":"1"}])
        data={"Quote Approval Dedup":records,
              "SFDC Quote Export":[],
              "SFDC Email Quotation Raw":quotes,
              "SFDC Email Ingest Audit":[{"Entity":"Quotation",
                  "Source Received KST":"2026-11-09 17:00:23 KST"}]}
        current=q.dt.datetime(2026,11,9,21,0,tzinfo=q.KST)
        with mock.patch.object(q,"validate_source",return_value="SOURCE_QQ_REPORT_VERIFIED"):
            listed=q.review_rows(data,now=current)
        self.assertEqual(len(listed),4)
        self.assertTrue(all(x["합산 상태"]==q.INCLUDED for x in listed))
        self.assertTrue(all(x["Active Evidence Source"]=="QQ_3REPORT_VERIFIED"
                            for x in listed))
        self.assertEqual(len(q.membership(listed)[1]["2026-11-06"]),4)

    def test_stale_export_and_stale_mail_mean_no_value_not_zero(self):
        data=source()
        old=q.dt.datetime(2026,11,9,21,0,tzinfo=q.KST)
        with mock.patch.object(q,"validate_source",return_value="WITHHELD_3REPORT_STALE"):
            rows=q.review_rows(data,now=old)
        self.assertTrue(all(r["제외 이유"]=="ACTIVE_NOT_VERIFIED" for r in rows))
        self.assertTrue(all(r["SFDC IsActive"]=="UNVERIFIED" for r in rows))

    def test_conflicting_quotation_active_rows_are_not_certified(self):
        data={"Quote Approval Dedup":[{"SFDC Record ID":A,
               "Approval KST":"2026-11-09 18:00:00",
               "Quotation Name":"QID-2026-11-09-412860"}],
              "SFDC Email Quotation Raw":[
                  {"SFDC Quotation ID":"QID-2026-11-09-412860","Active":"1"},
                  {"SFDC Quotation ID":"QID-2026-11-09-412860","Active":"0"}],
              "SFDC Email Ingest Audit":[{"Entity":"Quotation",
                "Source Received KST":"2026-11-09 17:00:23 KST"}]}
        with mock.patch.object(q,"validate_source",return_value="SOURCE_QQ_REPORT_VERIFIED"):
            row=q.review_rows(data,now=NOW)[0]
        self.assertEqual(row["제외 이유"],"ACTIVE_NOT_VERIFIED")
        self.assertEqual(row["Active Evidence Source"],"NO_VALUE")

    def test_strict_override_reader(self):
        self.assertTrue(q.checkbox(True))
        self.assertTrue(q.checkbox("true"))
        self.assertFalse(q.checkbox("FALSE"))
        self.assertFalse(q.checkbox(""))
        with self.assertRaisesRegex(SafeError,"UNEXPECTED_SOURCE_KEY"):
            q.read_overrides([{"fields":{"Source Key":"OTHER"}}])

if __name__=="__main__":
    unittest.main()
