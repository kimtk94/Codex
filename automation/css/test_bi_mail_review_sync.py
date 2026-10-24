"""Offline tests; never touch live Google Sheets."""
import contextlib
import io
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).with_name("bi_mail_review_sync.py")
spec=importlib.util.spec_from_file_location("bi_mail_review_sync",ROOT)
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class FakeValues:
    def __init__(self, records):
        self.records=records
        self.writes=[]
    def get(self,spreadsheetId,range,valueRenderOption):
        name=range.split("!")[0].strip("'")
        return FakeExecute({"values":self.records.get(name,[])})
    def batchUpdate(self,spreadsheetId,body):
        self.writes.append(("update",body))
        return FakeExecute({})
    def append(self,spreadsheetId,range,valueInputOption,insertDataOption,body):
        self.writes.append(("append",range,body["values"]))
        return FakeExecute({})

class FakeExecute:
    def __init__(self,result):
        self.result=result
    def execute(self):
        return self.result

class FakeSheets:
    def __init__(self,records):
        self.vals=FakeValues(records)
    def values(self):
        return self.vals

def source(uid,sender):
    row=[""]*21
    row[0]="3일"
    row[1]="10/22(목) 15:00"
    row[3]="Subject"
    row[8]=sender
    row[16]="subject"
    row[17]=uid
    row[20]="CUSTOMER_REVIEW"
    return row

def review(action,uid,sender,state="NOT_SUBMITTED"):
    return [action,sender,"Subject",3,uid,"REVIEW_2D","",state,"2026-10-24"]

class ReviewSyncTests(unittest.TestCase):
    def run_case(self,records,write=False):
        fake=FakeSheets(records)
        with patch.object(app,"auth",return_value=fake),patch.dict(os.environ,{"DRY_RUN":"false" if write else "true"}):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                if write:
                    app.main()
                else:
                    app.main()
        return fake.vals.writes,out.getvalue()

    def test_dry_run_does_not_write(self):
        records={app.REVIEW:[review("EXCLUDE_MAIL","inbox:1","a@test.com")],app.SOURCE:[source("inbox:1","a@test.com")],app.MAIL:[],app.SENDERS:[]}
        writes,out=self.run_case(records)
        self.assertEqual(writes,[])
        self.assertIn('"mail_exclusions_new": 1',out)

    def test_multiple_emails_from_one_sender_create_one_sender_exclusion(self):
        records={app.REVIEW:[review("EXCLUDE_SENDER","inbox:1","a@test.com"),review("EXCLUDE_SENDER","inbox:2","a@test.com")],app.SOURCE:[source("inbox:1","a@test.com"),source("inbox:2","a@test.com")],app.MAIL:[],app.SENDERS:[]}
        writes,out=self.run_case(records,True)
        sender=[w for w in writes if w[0]=="append" and app.SENDERS in w[1]]
        self.assertEqual(len(sender),1)
        self.assertEqual(len(sender[0][2]),1)
        self.assertIn('"synced": 2',out)

    def test_restore_existing_sender_flag(self):
        records={app.REVIEW:[review("RESTORE_SENDER","inbox:1","a@test.com")],app.SOURCE:[source("inbox:1","a@test.com")],app.MAIL:[],app.SENDERS:[[False,"a@test.com","exact"]]}
        writes,_=self.run_case(records,True)
        self.assertTrue(any(w[0]=="update" and any(app.SENDERS in d["range"] and d["values"]==[[True]] for d in w[1]["data"]) for w in writes))

    def test_new_uid_appears_without_overwriting_decision(self):
        records={app.REVIEW:[review("NONE","inbox:1","a@test.com")],app.SOURCE:[source("inbox:1","a@test.com"),source("inbox:2","b@test.com")],app.MAIL:[],app.SENDERS:[]}
        writes,_=self.run_case(records,True)
        add=[w for w in writes if w[0]=="append" and app.REVIEW in w[1]]
        self.assertEqual(len(add),1)
        self.assertEqual(len(add[0][2]),1)
        self.assertEqual(add[0][2][0][4],"inbox:2")

if __name__=="__main__":
    unittest.main()
