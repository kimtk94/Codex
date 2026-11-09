import copy
import unittest
from unittest.mock import patch
from sfdc_quote_reference_preindex import (
  preclassify,execute,TABLE_CLASS,TABLE_REFERENCE,ReportSourceError,
)
from test_sfdc_quote_report_bridge import data
from sfdc_quote_report_bridge import build_records


class ReferenceIndexTests(unittest.TestCase):
    def input(self):
        (lines,cols),heads=data()
        for idx,row in enumerate(lines):
            qid=row["SFDC Quotation ID"]
            suffix="1" if idx<2 else "2"
            row.update({
                "Contact Name: Full Name":"Sample Contact "+suffix,
                "Contact ID":"003000000000000AA"+suffix,
                "Email":"someone"+suffix+"@example.test",
                "Opportunity Name: Opportunity Name":"Korea-Service "+suffix,
                "Opportunity ID":"Opp-2026-11-10-"+suffix,
                "Account Name: Account Name":"Sample Institute "+suffix,
                "*Account Id":"001000000000000AA"+suffix,
                "Data Unit":"G raw data","Data Size":"6",
                "Sample Quantity":str(12+idx*15), # deliberately different
            })
        cols=list(dict.fromkeys(cols+[
            "Contact Name: Full Name","Contact ID","Email",
            "Opportunity Name: Opportunity Name","Opportunity ID",
            "Account Name: Account Name","*Account Id"
        ]))
        normalized=build_records((lines,cols),heads)
        provenance={"received_kst":"2026-11-09 17:00:23 KST",
            "source_sha256":"a"*64}
        return lines,normalized,provenance

    def test_shared_structure_and_gb_reuses_one_class_between_contacts(self):
        lines,normalized,provenance=self.input()
        a=preclassify(lines,normalized,provenance)
        self.assertEqual(a["summary"]["quote_references"],2)
        self.assertEqual(a["summary"]["quote_products"],2)
        self.assertEqual(a["summary"]["shared_project_classes"],1)
        refs=a["tables"][TABLE_REFERENCE]
        self.assertNotEqual(refs[0]["Contact ID"],refs[1]["Contact ID"])
        self.assertNotEqual(refs[0]["Account ID"],refs[1]["Account ID"])
        self.assertEqual(refs[0]["Account Contact Status"],"PASS")
        self.assertEqual(refs[1]["Account Contact Status"],"PASS")
        self.assertEqual(refs[0]["Source Received KST"],"2026-11-09 17:00:23 KST")
        # No user/customer prices or previous process quantities are part of class.
        self.assertEqual(len(a["tables"][TABLE_CLASS]),1)
        self.assertNotIn("Sample Qty",str(a["tables"][TABLE_CLASS]))

    def test_change_only_previous_quantities_cannot_change_class_key(self):
        lines,normalized,provenance=self.input()
        first=preclassify(lines,normalized,provenance)
        changed=copy.deepcopy(lines)
        for i,row in enumerate(changed):row["Sample Quantity"]=str(100000+i)
        again=preclassify(changed,normalized,provenance)
        self.assertEqual(first["tables"][TABLE_CLASS],again["tables"][TABLE_CLASS])

    def test_production_gb_change_changes_class_not_contact(self):
        lines,normalized,provenance=self.input()
        first=preclassify(lines,normalized,provenance)
        changed=copy.deepcopy(lines)
        for row in changed:
            if row["SFDC Quotation ID"]==changed[0]["SFDC Quotation ID"]:
                row["Data Size"]="12"
        again=preclassify(changed,normalized,provenance)
        self.assertEqual(len(first["tables"][TABLE_CLASS]),1)
        self.assertEqual(len(again["tables"][TABLE_CLASS]),2)

    def test_same_quote_conflicting_contact_id_becomes_hold(self):
        lines,normalized,provenance=self.input()
        new=copy.deepcopy(lines)
        new[1]["Contact ID"]="003000000000000AA9"
        result=preclassify(new,normalized,provenance)
        first=result["tables"][TABLE_REFERENCE][0]
        self.assertEqual(first["Account Contact Status"],"HOLD_IDENTITY")
        self.assertEqual(first["Contact ID"],"")

    def test_malformed_account_or_contact_id_cannot_be_verified(self):
        lines,normalized,provenance=self.input()
        for row in lines[:2]:row["*Account Id"]="not_an_account"
        result=preclassify(lines,normalized,provenance)
        self.assertEqual(result["tables"][TABLE_REFERENCE][0]["Account ID"],"")
        self.assertEqual(result["summary"]["account_contact_hold"],1)

    def test_audit_mode_never_creates_feishu_tables(self):
        lines,normalized,provenance=self.input()
        pre=preclassify(lines,normalized,provenance)
        with patch("sfdc_quote_reference_preindex.load_source",return_value=pre):
            with patch("sfdc_quote_reference_preindex.auth") as auth:
                result=execute("audit")
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(result["feishu_writes"],0)
        auth.assert_not_called()


if __name__=="__main__":unittest.main()
