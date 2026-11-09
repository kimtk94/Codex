"""Synthetic only: Feishu Report mirror preserves line-level rates across contacts."""
import copy
import unittest
from unittest.mock import patch

from sfdc_quote_report_bridge import (
    build_records,verify_qq_process_report_audit,ReportSourceError,TABLE_PROCESS,TABLE_PRODUCT,TABLE_LINES,
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
    def _mail_audit(self):
        import hashlib,json
        source,_=data()
        lines,headers=source
        digest=hashlib.sha256(json.dumps(
            [headers,[[row.get(h,"") for h in headers] for row in lines]],
            ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        audit={
            "Entity":"Quotation",
            "Source Received KST":"2026-11-09 17:00:23 KST",
            "Ingest Checked KST":"2026-11-10 00:35:37 KST",
            "Rows":str(len(lines)),
            "Unique IDs":str(len({r["SFDC Quotation ID"] for r in lines})),
            "Duplicate IDs":str(len(lines)-len({r["SFDC Quotation ID"] for r in lines})),
            "Missing IDs":"0",
            "Content SHA256":digest,"State":"PRESERVED_NO_NEW_REPORT",
            "Source Kind":"QQ IMAP",
        }
        return source,([audit],list(audit))

    def test_qq_mail_sha_and_receipt_provenance(self):
        source,audit=self._mail_audit()
        proof=verify_qq_process_report_audit(source,audit)
        self.assertTrue(proof["source_mail_hash_verified"])
        self.assertEqual(proof["received_kst"],"2026-11-09 17:00:23 KST")
        self.assertEqual(proof["audit_state"],"PRESERVED_NO_NEW_REPORT")
        records=build_records(source,data()[1],verified_evidence=proof)
        self.assertTrue(records["summary"]["source_mail_timestamp_verified"])
        self.assertTrue(records["summary"]["source_mail_hash_verified"])
        self.assertFalse(records["summary"]["process_report_export_time_verified"])
        self.assertTrue(all(x["Source Received KST"]==proof["received_kst"]
                            and x["Source Exported KST"]==""
                            for x in records["tables"][TABLE_LINES]))

    def test_qq_mail_sha_detects_stale_or_edited_sheet(self):
        source,audit=self._mail_audit()
        source[0][0]["Unit Price USD"]="9999"
        with self.assertRaisesRegex(ReportSourceError,"QUOTE_MAIL_AUDIT_HASH_MISMATCH"):
            verify_qq_process_report_audit(source,audit)

    def test_qq_mail_provenance_rejects_false_source_counters(self):
        source,audit=self._mail_audit()
        audit[0][0]["Rows"]="9999"
        with self.assertRaisesRegex(ReportSourceError,"QUOTE_MAIL_AUDIT_COUNT_MISMATCH"):
            verify_qq_process_report_audit(source,audit)

    def test_qq_mail_provenance_rejects_untrusted_source(self):
        source,audit=self._mail_audit()
        audit[0][0]["Source Kind"]="Manual CSV"
        with self.assertRaisesRegex(ReportSourceError,"QUOTE_MAIL_AUDIT_STATE_UNVERIFIED"):
            verify_qq_process_report_audit(source,audit)

    def test_received_time_not_confused_with_old_quote_header(self):
        source,audit=self._mail_audit()
        received=verify_qq_process_report_audit(source,audit)
        output=build_records(source,data()[1],verified_evidence=received)
        values=output["tables"]
        self.assertTrue(all(row["Source Received KST"]=="2026-11-09 17:00:23 KST"
                            for rows in values.values() for row in rows))
        self.assertTrue(all(row["Source Exported KST"]==""
                            for rows in values.values() for row in rows))
        self.assertEqual(output["summary"]["status"],
                         "MAIL_RECEIPT_VERIFIED_EXPORT_UNVERIFIED")
        self.assertTrue(all(x["Source Status"]==
                            "MAIL_RECEIPT_VERIFIED_EXPORT_UNVERIFIED"
                            for x in values[TABLE_LINES]))

    def test_prior_mail_receipt_cannot_be_downgraded(self):
        row={"Line Key":"l1","Source Exported KST":"",
             "Source Received KST":"2026-11-09 17:00:23 KST",
             "Source Status":"MAIL_RECEIPT_VERIFIED_EXPORT_UNVERIFIED"}
        old={"record_id":"rec1","fields":dict(row,
              **{"Source Received KST":"2026-11-10 01:00:00 KST"})}
        with patch("sfdc_quote_report_bridge.path",return_value="/apps/test"):
            with patch("sfdc_quote_report_bridge.pages",return_value=[old]):
                with self.assertRaisesRegex(ReportSourceError,"FEISHU_MAIL_RECEIPT_REGRESSION"):
                    sync_one("token","tid","Line Key",[row])

    def test_add_only_verified_source_received_field_to_owned_mirror(self):
        from sfdc_quote_report_bridge import ensure_table
        old=[{"field_name":"Process Key","type":1},
             {"field_name":"Process ID","type":1},
             {"field_name":"Process Name","type":1},
             {"field_name":"Data Unit","type":1},
             {"field_name":"Source Exported KST","type":1}]
        new=old+[{"field_name":"Source Received KST","type":1}]
        with patch("sfdc_quote_report_bridge.list_tables",
                   return_value={"SFDC Quote Process Dictionary":{"table_id":"tbl_a"}}):
            with patch("sfdc_quote_report_bridge.path",return_value="/apps/base"):
                with patch("sfdc_quote_report_bridge.pages",side_effect=[old,new]):
                    with patch("sfdc_quote_report_bridge.call",
                               return_value={"field":{"field_name":"Source Received KST","type":1}}) as created:
                        table=ensure_table("token","SFDC Quote Process Dictionary")
        self.assertEqual(table,"tbl_a")
        self.assertEqual(created.call_count,1)
        self.assertEqual(created.call_args.args[1],"/apps/base/tables/tbl_a/fields")
        self.assertEqual(created.call_args.args[3]["field_name"],"Source Received KST")

    def test_qq_mail_provenance_rejects_future_receipt(self):
        source,audit=self._mail_audit()
        audit[0][0]["Source Received KST"]="2099-01-01 00:00:00 KST"
        with self.assertRaisesRegex(ReportSourceError,"QUOTE_MAIL_AUDIT_FUTURE_TIMESTAMP"):
            verify_qq_process_report_audit(source,audit)

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

    def test_template_legacy_header_stamp_exact_match_only(self):
        previous={"Process Key":"process-hash",
                  "Source Exported KST":EXPORTED}
        after={"Process Key":"process-hash","Source Exported KST":""}
        with patch("sfdc_quote_report_bridge.path",return_value="/apps/test"):
            with patch("sfdc_quote_report_bridge.pages",
                       side_effect=[[{"record_id":"record1","fields":previous}],
                                    [{"record_id":"record1","fields":after}]]):
                with patch("sfdc_quote_report_bridge.write_batch",
                           return_value=[{"record_id":"record1","fields":after}]):
                    result=sync_one("t","tbl","Process Key",[after],
                                    legacy_header_exported_kst=EXPORTED)
        self.assertEqual(result["updated"],1)
        self.assertEqual(result["readback"],"PASS")
        with patch("sfdc_quote_report_bridge.path",return_value="/apps/test"):
            with patch("sfdc_quote_report_bridge.pages",
                       return_value=[{"record_id":"record1","fields":previous}]):
                with self.assertRaisesRegex(ReportSourceError,"FEISHU_REPORT_SOURCE_REGRESSION"):
                    sync_one("t","tbl","Process Key",[after],
                             legacy_header_exported_kst="2026-01-01 00:00:00 KST")

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

    def test_old_source_only_lines_retained_but_marked_superseded(self):
        latest={"Line Key":"current-hash","Source Status":"DETAIL_REPORT_TIME_UNVERIFIED",
                "Source Exported KST":""}
        prior={"record_id":"live1","fields":dict(latest)}
        old={"record_id":"historic1","fields":{"Line Key":"old-hash",
                "Source Status":"STALE","Source Exported KST":EXPORTED}}
        retired={"record_id":"historic1","fields":dict(old["fields"],
            **{"Source Status":"SUPERSEDED_NOT_IN_CURRENT_REPORT"})}
        with patch("sfdc_quote_report_bridge.path",return_value="/apps/test"):
            with patch("sfdc_quote_report_bridge.pages",
                       side_effect=[[prior,old],[prior,retired]]):
                with patch("sfdc_quote_report_bridge.write_batch",
                           return_value=[retired]):
                    result=sync_one("t","tbl","Line Key",[latest])
        self.assertEqual(result["source_rows"],1)
        self.assertEqual(result["superseded"],1)
        self.assertEqual(result["historical_retained_rows"],1)
        self.assertEqual(result["physical_feishu_rows"],2)
        self.assertEqual(result["readback"],"PASS")

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
