"""Offline tests for Feishu-authenticated Quote Report source and private cache."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sfdc_feishu_report_local as f


def sha(x):
    return hashlib.sha256(x.encode()).hexdigest()


def evidence():
    process_key=sha("process1")
    template_key=sha("rna_library")
    process=[{"Process Key":process_key,
        "Process ID":"Process-2020-01-01-00001",
        "Process Name":"Library Preparation","Data Unit":"sample",
        "Source Exported KST":"","Source Received KST":"2026-10-24 18:00:08 KST"}]
    product=[{"Product Template Key":template_key,
        "Process Keys":json.dumps([process_key]),
        "Process Count":"1","Source Exported KST":"","Source Received KST":"2026-10-24 18:00:08 KST"}]
    lines=[]
    for i,price in enumerate(("190","210")):
        lines.append({
            "Line Key":sha("line"+str(i)),
            "Quote ID":"QID-2026-10-20-00000"+str(i),
            "Quote Record ID":"a0P000000000000AA"+str(i),
            "Quote Product ID":"QD-11111"+str(i),
            "Product Template Key":template_key,
            "Process Key":process_key,
            "Unit Price USD":price,
            "Sales Price USD":price,
            "Process Total USD":str(20*int(price)),
            "Sample Qty":"20","Data Size":"6",
            "Active":"1","Quote Created":"10/20/2026",
            "Source Exported KST":"",
            "Source Received KST":"2026-10-24 18:00:08 KST",
            "Source Row Hash":sha("original"+str(i)),
            "Source Status":"MAIL_RECEIPT_VERIFIED_EXPORT_UNVERIFIED",
        })
    return lines,process,product


class FeishuReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        p1=patch.object(f,"DB_DIR",base)
        p2=patch.object(f,"DB_PATH",base/"private.sqlite3")
        p1.start()
        p2.start()
        self.addCleanup(p2.stop)
        self.addCleanup(p1.stop)

    def test_feishu_cell_format(self):
        self.assertEqual(f._text({"value":[{"type":"text","text":"190.00"}]}),"190.00")
        self.assertEqual(f._text({"value":None}),"")
        with self.assertRaises(f.FeishuSourceError):
            f._text({"value":{"unexpected":"x"}})

    def test_same_product_shared_but_quote_prices_independent(self):
        data=evidence()
        m=f._validate(*data)
        self.assertEqual(m["quote_count"],2)
        self.assertEqual(m["product_count"],2)
        self.assertEqual(m["product_templates"],1)
        with patch.object(f,"_read_all_from_browser",return_value=(*data,
               {"lines":19,"process":2,"product":3},0.1)):
            r=f.refresh()
        self.assertEqual(r["status"],"PASS")
        self.assertEqual(r["feishu_sink_readback"],"PASS")
        self.assertEqual(r["feishu_writes"],0)
        s=f.search("",25)
        self.assertEqual(len(s["rows"]),2)
        self.assertEqual(f.detail(data[0][0]["Quote ID"])["process_lines"][0]["unit_price_usd"],"190")
        self.assertEqual(f.detail(data[0][1]["Quote ID"])["process_lines"][0]["unit_price_usd"],"210")
        self.assertFalse(f.status()["krw_rate_verified"])
        self.assertEqual(f.status()["source_state"],"STALE_MAIL_SOURCE")
        self.assertEqual(f.status()["source_mail_received_kst"],"2026-10-24 18:00:08 KST")
        self.assertFalse(f.status()["process_export_time_verified"])

    def test_missing_feishu_received_timestamp_blocks_publication(self):
        data=list(evidence())
        data[0][0]["Source Received KST"]=""
        with self.assertRaisesRegex(f.FeishuSourceError,
                                     "FEISHU_MAIL_RECEIPT_SOURCE_MISSING"):
            f._validate(*data)

    def test_different_source_mail_timestamps_block_snapshot(self):
        data=list(evidence())
        data[0][0]["Source Received KST"]="2026-11-09 17:00:23 KST"
        with self.assertRaisesRegex(f.FeishuSourceError,
                                     "FEISHU_MAIL_RECEIPT_SOURCE_MISSING"):
            f._validate(*data)

    def test_unreadable_sfdc_record_id_blocks_before_cache_swap(self):
        data=list(evidence())
        data[0][0]["Quote Record ID"]="another"
        with self.assertRaisesRegex(f.FeishuSourceError,"FEISHU_NATIVE_QUOTE_ID_INVALID"):
            f._validate(*data)
        self.assertEqual(f.status()["status"],"BLOCK")

    def test_missing_product_process_ref_blocks_before_cache_swap(self):
        data=list(evidence())
        data[0][0]["Process Key"]=sha("missing")
        with self.assertRaisesRegex(f.FeishuSourceError,"FEISHU_REFERENCE_MISSING"):
            f._validate(*data)

    def test_malformed_amount_never_promoted(self):
        data=list(evidence())
        data[0][0]["Unit Price USD"]="NaN"
        with self.assertRaisesRegex(f.FeishuSourceError,"FEISHU_AMOUNT_INVALID"):
            f._validate(*data)

    def test_no_write_modes(self):
        for val in ("SAVE","DELETE","WRITE","UPSERT"):
            with self.assertRaisesRegex(f.FeishuSourceError,"FEISHU_READ_ONLY_MODE_REQUIRED"):
                f.run({"mode":val})

    def test_no_implicit_sheet_fallback_when_feishu_absent(self):
        self.assertEqual(f.status()["code"],"FEISHU_REPORT_NOT_SYNCED")
        with self.assertRaisesRegex(f.FeishuSourceError,"FEISHU_REPORT_NOT_SYNCED"):
            f.search("QID",10)


if __name__=="__main__":
    unittest.main()
