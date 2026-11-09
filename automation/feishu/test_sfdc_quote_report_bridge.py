"""Synthetic only: Feishu Report mirror preserves line-level rates across contacts."""
import copy
import unittest
from unittest.mock import patch

from sfdc_quote_report_bridge import (
    build_records,ReportSourceError,TABLE_PROCESS,TABLE_PRODUCT,TABLE_LINES,
    sync_one,execute,
)

EXPORTED="2026-10-24 18:00:08 KST"
Q1="QID-2026-10-20-200101"
Q2="QID-2026-10-20-200102"

LINE_HEAD=[
 "SFDC Quotation ID","Quotation Product ID","Process Name: SFDC Process ID",
 "Quote Process Name","Data Unit","Unit Price USD",
 "Total Price USD (converted)","Sample Quantity","Data Size",
 "Active","Created Date","Sales Price USD (converted)"
]
HEAD_HEAD=["AMEA Quotation ID","Salesforce Record ID","Exported At KST"]


def data():
    headers=[
        {"AMEA Quotation ID":Q1,"Salesforce Record ID":"a0PTK0000000001AAA",
         "Exported At KST":EXPORTED},
        {"AMEA Quotation ID":Q2,"Salesforce Record ID":"a0PTK0000000002AAA",
         "Exported At KST":EXPORTED}
    ]
    lines=[]
    for qid,product,price,qty in [
        (Q1,"QD-1001","110","20"),
        (Q2,"QD-1002","190","20"),
    ]:
        for proc,name,amount in [
            ("Process-001","RNA Library",price),
            ("Process-002","AliCloud","35"),
        ]:
            lines.append({
                "SFDC Quotation ID":qid,
                "Quotation Product ID":product,
                "Process Name: SFDC Process ID":proc,
                "Quote Process Name":name,
                "Data Unit":"sample" if proc=="Process-001" else "100 Gb",
                "Unit Price USD":amount,
                "Total Price USD (converted)":amount,
                "Sample Quantity":qty if proc=="Process-001" else "2",
                "Data Size":"12","Active":"1","Created Date":"10/23/2026",
                "Sales Price USD (converted)":amount
            })
    return (lines,LINE_HEAD),(headers,HEAD_HEAD)


class ReportBridgeTests(unittest.TestCase):
    def test_repeated_product_line_dedup_keeps_contact_quotes_distinct(self):
        output=build_records(*data())
        self.assertEqual(output["summary"]["quote_count"],2)
        self.assertEqual(output["summary"]["report_lines"],4)
        self.assertEqual(output["summary"]["process_templates"],2)
        self.assertEqual(output["summary"]["product_templates"],1)
        self.assertFalse(output["summary"]["krw_rate_verified"])
        rows=output["tables"][TABLE_LINES]
        self.assertEqual(len({r["Line Key"] for r in rows}),4)
        self.assertEqual(rows[0]["Product Template Key"],rows[2]["Product Template Key"])
        self.assertEqual(rows[0]["Unit Price USD"],"110")
        self.assertEqual(rows[2]["Unit Price USD"],"190")
        self.assertEqual(rows[0]["Quote Record ID"],"a0PTK0000000001AAA")
        self.assertEqual(rows[2]["Quote Record ID"],"a0PTK0000000002AAA")

    def test_duplicate_process_line_keeps_unique_instance_keys(self):
        (lines,lh),headers=data()
        lines.append(copy.deepcopy(lines[0]))
        result=build_records((lines,lh),headers)
        self.assertEqual(len({x["Line Key"] for x in result["tables"][TABLE_LINES]}),5)
        self.assertEqual(result["summary"]["report_lines"],5)

    def test_unmatched_quote_report_is_kept_with_explicit_unverified_id(self):
        (lines,lh),headers=data()
        lines[0]["SFDC Quotation ID"]="QID-2026-10-20-999999"
        output=build_records((lines,lh),headers)
        self.assertEqual(output["summary"]["report_lines"],4)
        self.assertEqual(output["summary"]["quote_record_ids_unmapped"],1)
        unmatched=next(x for x in output["tables"][TABLE_LINES]
                       if x["Quote ID"]=="QID-2026-10-20-999999")
        self.assertEqual(unmatched["Quote Record ID"],"")
        self.assertEqual(unmatched["Source Status"],"QUOTE_RECORD_ID_UNVERIFIED")
        self.assertEqual(unmatched["Source Exported KST"],"")
        self.assertFalse(output["summary"]["process_report_export_time_verified"])

    def test_export_timestamp_conflict_blocks(self):
        source,head=data()
        head[0][1]["Exported At KST"]="2026-10-25 18:00:08 KST"
        with self.assertRaisesRegex(ReportSourceError,"REPORT_EXPORT_TIME_CONFLICT"):
            build_records(source,(head[0],head[1]))

    def test_new_header_cannot_relabel_old_process_lines_fresh(self):
        """Header email alone cannot certify process report export timestamp."""
        source,(headers,names)=data()
        for header in headers:
            header["Exported At KST"]="2026-11-09 18:00:08 KST"
        result=build_records(source,(headers,names))
        self.assertFalse(result["summary"]["process_report_export_time_verified"])
        self.assertEqual(result["summary"]["status"],"DETAIL_REPORT_TIME_UNVERIFIED")
        self.assertTrue(all(row["Source Exported KST"]==""
                            for row in result["tables"][TABLE_LINES]))
        self.assertEqual(result["summary"]["header_exported_kst"],
                         "2026-11-09 18:00:08 KST")

    def test_report_input_missing_product_price_fails(self):
        (lines,lh),heads=data()
        del lines[0]["Unit Price USD"]
        with self.assertRaisesRegex(ReportSourceError,"REPORT_NUMBER"):
            # Non-numeric value must not be promoted to a valid unit price.
            lines[0]["Unit Price USD"]="NOT_NUMERIC"
            build_records((lines,lh),heads)

    def test_legacy_header_time_can_be_cleared_only_when_unverified(self):
        row={"Line Key":"same","Quote ID":Q1,"Source Exported KST":"",
             "Source Status":"DETAIL_REPORT_TIME_UNVERIFIED"}
        prior={"record_id":"rec1","fields":dict(row,
             **{"Source Exported KST":EXPORTED,"Source Status":"STALE"})}
        after={"record_id":"rec1","fields":row}
        with patch("sfdc_quote_report_bridge.path",return_value="/apps/test"):
            with patch("sfdc_quote_report_bridge.pages",side_effect=[[prior],[after]]):
                with patch("sfdc_quote_report_bridge.write_batch",
                           return_value=[{"record_id":"rec1","fields":row}]):
                    result=sync_one("t","tbl","Line Key",[row])
        self.assertEqual(result["updated"],1)
        self.assertEqual(result["readback"],"PASS")

    def test_verified_previous_source_timestamp_never_downgrades(self):
        row={"Line Key":"same","Quote ID":Q1,"Source Exported KST":"",
             "Source Status":"DETAIL_REPORT_TIME_UNVERIFIED"}
        prior={"record_id":"rec1","fields":dict(row,
             **{"Source Exported KST":EXPORTED,"Source Status":"VERIFIED"})}
        with patch("sfdc_quote_report_bridge.path",return_value="/apps/test"):
            with patch("sfdc_quote_report_bridge.pages",return_value=[prior]):
                with self.assertRaisesRegex(ReportSourceError,
                                             "FEISHU_REPORT_SOURCE_REGRESSION"):
                    sync_one("t","tbl","Line Key",[row])

    def test_empty_created_dates_are_held_not_fatal(self):
        (lines,lh),headers=data()
        lines[0]["Created Date"]="null"
        output=build_records((lines,lh),headers)
        self.assertEqual(output["summary"]["process_date_missing_rows"],1)
        self.assertEqual(output["summary"]["report_lines"],4)

    def test_audit_never_calls_feishu_writer(self):
        with patch("sfdc_quote_report_bridge.load_source",return_value=build_records(*data())):
            with patch("sfdc_quote_report_bridge.auth") as auth:
                audit=execute("audit")
        self.assertEqual(audit["status"],"PASS")
        self.assertEqual(audit["feishu_writes"],0)
        auth.assert_not_called()

    def test_upsert_reuses_existing_exact_line(self):
        qid="QID-2026-10-20-200101"
        records=[{"Line Key":"hash1","Quote ID":qid,"Source Exported KST":EXPORTED}]
        current=[{"record_id":"rec0000001","fields":dict(records[0])}]
        with patch("sfdc_quote_report_bridge.path",return_value="/apps/test"):
            with patch("sfdc_quote_report_bridge.pages",side_effect=[current,current]) as read:
                with patch("sfdc_quote_report_bridge.write_batch") as writer:
                    result=sync_one("token","tbl0","Line Key",records)
        self.assertEqual(result["unchanged"],1)
        self.assertEqual(result["readback"],"PASS")
        writer.assert_not_called()
        self.assertEqual(read.call_count,2)


if __name__=="__main__":
    unittest.main()
