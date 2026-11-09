"""Synthetic offline tests for private SFDC Quotation Report index."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sfdc_quote_report_sheet as sheet
import sfdc_quote_report_index as local

QID1="QID-2026-11-09-000001"
QID2="QID-2026-11-09-000002"
RECORD1="a0P000000000000"
COLS=sheet.HEADER


def raw(qid,product,unit,contact,account,date="11/9/2026",currency="USD"):
    values={k:"" for k in COLS}
    values.update({
        "SFDC Quotation ID":qid,"Quotation Product ID":product,
        "Contact Name: Full Name":contact,"Contact ID":"CP1" if contact=="A" else "CP2",
        "Opportunity Name: Opportunity Name":"Synthetic-"+contact,
        "Opportunity ID":"Opp-2026-11-09-00000"+("1" if contact=="A" else "2"),
        "Account Name: Account Name":account,"*Account Id":"001000000000000AAA",
        "Active":"1","Sync CMS":"1",
        "Opportunity Amount USD":"1500",
        "Total Price USD (converted) Currency":currency,
        "Total Price USD (converted)":"300",
        "Sales Price USD (converted) Currency":"USD",
        "Sales Price USD (converted)":"300",
        "Unit Price USD":unit,
        "Quotation Process Name":"Library preparation,AliCloud",
        "Process Name: SFDC Process ID":"Process-2020-04-30-00044",
        "Quote Process Name":"Library preparation",
        "Created Date":date,"Data Unit":"G raw data",
        "Sample Quantity":"12","Data Size":"12"
    })
    return [values[k] for k in COLS]


class SheetTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        staging=root/"quote_report_sheet_sync"
        staging.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(sheet,"STAGING",staging).start()
        patch.object(sheet,"DB_DIR",root).start()
        patch.object(sheet,"SHEET_DB",root/"sheet.sqlite3").start()
        patch.object(sheet,"_identity_map",return_value={QID1:RECORD1}).start()
        self.root=staging

    def write(self,rows,first=2,last=None):
        name="part_000.json"
        doc={"source":"SFDC_Email_Quotation_Raw","sheet_id":sheet.SHEET_ID,
            "first_row":first,"last_row":first+len(rows)-1 if last is None else last,
            "rows":rows}
        (self.root/name).write_text(json.dumps(doc,ensure_ascii=False),encoding="utf-8")

    def test_repeat_process_dictionary_but_not_customer_prices(self):
        self.write([
            raw(QID1,"QD-1","190.00","A","Example Univ A"),
            raw(QID2,"QD-2","240.00","B","Example Univ B"),
            raw(QID2,"QD-3","35.00","B","Example Univ B")])
        result=sheet.sync_staged()
        self.assertEqual(result["status"],"PASS")
        self.assertEqual((result["quote_count"],result["process_rows"]), (2,3))
        self.assertEqual(result["unique_process_definitions"],1)
        self.assertEqual(result["product_count"],3)
        self.assertEqual(result["linked_sfdc_record_count"],1)
        self.assertEqual(result["unmapped_sfdc_record_count"],1)
        self.assertEqual(result["newest_quote_created_date"],"2026-11-09")
        self.assertFalse(result["krw_rate_verified"])
        a=sheet.detail(QID1)
        b=sheet.detail(QID2)
        self.assertEqual(a["process_lines"][0]["unit_price_usd"],"190.00")
        self.assertEqual(b["process_lines"][0]["unit_price_usd"],"240.00")
        self.assertNotEqual(a["contact_name"],b["contact_name"])
        self.assertEqual(a["sfdc_record_id"],RECORD1)
        self.assertIsNone(b["sfdc_record_id"])
        self.assertEqual(sheet.detail(RECORD1)["qid"],QID1)
        self.assertEqual(len(sheet.search("Example Univ B")["rows"]),1)

    def test_wrong_currency_fail_closed(self):
        self.write([raw(QID1,"QD-1","190","A","A",currency="KRW")])
        with self.assertRaisesRegex(local.ReportError,"SHEET_CURRENCY_NOT_USD"):
            sheet.sync_staged()

    def test_missing_chunk_is_not_silently_accepted(self):
        self.write([raw(QID1,"QD-1","190","A","A")],first=3)
        with self.assertRaisesRegex(local.ReportError,"SHEET_PART_SEQUENCE_INVALID"):
            sheet.load_staged_chunks()

    def test_sheet_unverified_new_quote_id_cannot_be_guessed(self):
        self.write([raw(QID2,"QD-2","190","B","B")])
        sheet.sync_staged()
        with self.assertRaisesRegex(local.ReportError,"SHEET_SFDC_ID_UNMAPPED"):
            sheet.detail("a0P00000000000X")

    def test_gzipped_stage_has_same_source_line_integrity(self):
        import gzip
        self.write([raw(QID1,"QD-1","190.00","A","A")])
        src=self.root/"part_000.json"
        z=self.root/"part_000.json.gz"
        z.write_bytes(gzip.compress(src.read_bytes(),compresslevel=9))
        src.unlink()
        result=sheet.sync_staged()
        self.assertEqual(result["process_rows"],1)
        self.assertEqual(sheet.detail(QID1)["process_lines"][0]["unit_price_usd"],"190.00")

    def test_no_deduplication_of_money_fields(self):
        self.write([raw(QID1,"QD-1","190.01","A","A"),
                    raw(QID1,"QD-1","0.00","A","A")])
        sheet.sync_staged()
        got=sheet.detail(QID1)
        self.assertEqual([x["unit_price_usd"] for x in got["process_lines"]],
                         ["190.01","0.00"])


if __name__=="__main__":
    unittest.main()
