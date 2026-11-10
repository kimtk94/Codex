"""Fail-closed tests of the Feishu preclassified local Quote reference cache."""
import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import sfdc_feishu_preclassified_local as idx
import sfdc_feishu_report_local as base

def h(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

class PreclassifiedLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"quote.sqlite3"
        db=sqlite3.connect(self.db)
        try:
            db.execute("CREATE TABLE quote_lines(qid TEXT,quote_product TEXT)")
            db.executemany("INSERT INTO quote_lines VALUES(?,?)",[
                ("QID-2026-11-09-001001","QD-1"),
                ("QID-2026-11-09-001002","QD-2")
            ])
            db.commit()
        finally:
            db.close()
        p1=patch.object(base,"_connect",lambda:sqlite3.connect(self.db))
        p2=patch.object(idx,"DB",Path(self.tmp.name)/"preindex.sqlite3")
        p1.start();p2.start()
        self.addCleanup(p2.stop);self.addCleanup(p1.stop)
        self.quote_ids=["QID-2026-11-09-001001","QID-2026-11-09-001002"]
        self.base={"quote_count":2,"product_count":2,
                   "source_mail_received_kst":"2026-11-09 17:00:23 KST"}

    def fixture(self):
        ckey=h(["template","6"])
        classes=[{"Class Key":ckey,"Product Template Key":"1"*64,
                  "Production Gb":"6","Gb Status":"PASS",
                  "Source Exported KST":"",
                  "Source Received KST":self.base["source_mail_received_kst"]}]
        rows=[]
        for n,qid in enumerate(self.quote_ids):
            record={"Quote ID":qid,"Quote Record ID":"a0P000000000000AA"+str(n),
                "Opportunity External ID":"Opp-2026-11-09-"+str(n),
                "Opportunity Name":"Test project "+str(n),
                "Account ID":"001000000000000AA"+str(n),
                "Account Name":"Synthetic University "+str(n),
                "Contact ID":"",
                "Contact External ID":"CP2024000000"+str(n),
                "Contact Name":"Synthetic Contact "+str(n),
                "Contact Email":"example"+str(n)+"@invalid.test",
                "Account Contact Status":"CONTACT_EXTERNAL_ONLY",
                "Products JSON":json.dumps([{"classKey":ckey,"quoteProductId":"QD-"+str(n+1),
                "productionGb":"6","gbStatus":"PASS","referenceTotalUsd":"1000.00"}],
                sort_keys=True,ensure_ascii=False,separators=(",",":")),
                "Product Count":"1",
                "Reference Status":"HOLD","Source Exported KST":"",
                "Source Received KST":self.base["source_mail_received_kst"]}
            record["Reference SHA256"]=h(record)
            rows.append(record)
        return rows,classes

    def test_shared_class_two_quote_refs_and_contact_external_preserved(self):
        rows,classes=self.fixture()
        refs,keys=idx._verified_refs(rows,classes,self.base)
        self.assertEqual(len(refs),2)
        self.assertEqual(len(keys),1)
        self.assertNotEqual(refs[self.quote_ids[0]][0]["Contact External ID"],
                            refs[self.quote_ids[1]][0]["Contact External ID"])

    def test_tampered_reference_fails_closed(self):
        rows,classes=self.fixture()
        rows[0]["Account Name"]="tampered"
        with self.assertRaisesRegex(base.FeishuSourceError,"CHECKSUM_MISMATCH"):
            idx._verified_refs(rows,classes,self.base)

    def test_missing_quote_product_class_rejected(self):
        rows,classes=self.fixture()
        rows[0]["Products JSON"]=json.dumps([{
            "classKey":"f"*64,"quoteProductId":"QD-1"}])
        rows[0]["Reference SHA256"]=h({k:v for k,v in rows[0].items() if k!="Reference SHA256"})
        with self.assertRaisesRegex(base.FeishuSourceError,"CLASS_REF_MISSING"):
            idx._verified_refs(rows,classes,self.base)

    def test_mail_date_mismatch_invalidates_reference_cache(self):
        rows,classes=self.fixture()
        rows[0]["Source Received KST"]="2026-11-08 17:00:23 KST"
        rows[0]["Reference SHA256"]=h({k:v for k,v in rows[0].items() if k!="Reference SHA256"})
        with self.assertRaisesRegex(base.FeishuSourceError,"SOURCE_TIME_MISMATCH"):
            idx._verified_refs(rows,classes,self.base)

    def test_identity_picker_preserves_same_name_different_institutions(self):
        cx=sqlite3.connect(str(idx.DB))
        try:
            cx.execute("""CREATE TABLE quote_reference(
                qid TEXT,account_id TEXT,account_name TEXT,contact_id TEXT,
                contact_external_id TEXT,contact_name TEXT,contact_email TEXT,
                identity_status TEXT)""")
            cx.executemany("INSERT INTO quote_reference VALUES(?,?,?,?,?,?,?,?)",[
                ("QID-2026-11-09-000101","001000000000000AA0","Alpha Univ",
                 "003000000000000AA0","","Kim Min","one@invalid.test","VERIFIED"),
                ("QID-2026-11-09-000102","001000000000000AA1","Beta Univ",
                 "003000000000000AA1","","Kim Min","two@invalid.test","VERIFIED"),
                ("QID-2026-11-09-000103","001000000000000AA1","Beta Univ",
                 "003000000000000AA1","","Kim Min","two@invalid.test","VERIFIED"),
            ])
            cx.commit()
        finally:cx.close()
        with patch.object(idx,"status",return_value={"status":"PASS"}):
            result=idx.identity_candidates("Kim Min")
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(len(result["rows"]),2)
        self.assertEqual({x["account_name"] for x in result["rows"]},
                         {"Alpha Univ","Beta Univ"})
        self.assertTrue(all(x["crm_contact_verified"] for x in result["rows"]))
        self.assertFalse(result["salesforce_write"])

    def test_identity_picker_requires_bounded_nonempty_query(self):
        with patch.object(idx,"status",return_value={"status":"PASS"}):
            for term in ("","   ","a"*81):
                with self.assertRaisesRegex(base.FeishuSourceError,"IDENTITY_QUERY_INVALID"):
                    idx.identity_candidates(term)
            with self.assertRaisesRegex(base.FeishuSourceError,"IDENTITY_QUERY_INVALID"):
                idx.identity_candidates("Kim",limit=300)

    def test_missing_sqlite_returns_block(self):
        self.assertEqual(idx.status()["status"],"BLOCK")


if __name__=="__main__":unittest.main()
