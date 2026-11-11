import unittest
from unittest.mock import patch
from sfdc_quote_edit_probe import audit_controls_snapshot
from sfdc_pair_web_preview import run

OPP="006000000000000AAA"
QUOTE="a0P000000000000AAA"
HEADER=["","","Pack No.","Process Name","Process Type","Sample Number",
        "Data Size","Data Unit","Unit Price","Standard Price","Note","",""]
SOURCE=[
 {"packNo":"Package1","processType":"Library preparation",
  "processName":"mRNA library preparation (poly A enrichment)",
  "sourceQty":12,"unitPriceKrw":160000,"isCloud":False},
 {"packNo":"Package1","processType":"Sequencing by data amount",
  "processName":"NovaSeq X Plus (PE150)","sourceQty":12,"unitPriceKrw":0,"isCloud":False},
 {"packNo":"","processType":"Data release",
  "processName":"AliCloud","sourceQty":1,"unitPriceKrw":35000,"isCloud":True}
]
FLAGS={"pack_button":1,"unpack_button":1,"cancel_button":1}
OBSERVED=[
 {**x,"qty":x["sourceQty"],"price_input_count":1,"price_editable":True,
  "qty_input_count":1,"qty_editable":x["isCloud"]} for x in SOURCE
]
FORM={"mode":"CHECK_WRITE_CONTROLS","runMode":"CHECK",
 "sourceOpportunityId":OPP,"sourceQuoteId":QUOTE,
 "newOpportunityName":"Korea-Original-Quote-New",
 "samples":12,"dataSizeGb":5,
 "productUnitOverrideKrw":"","cloudUnitOverrideKrw":""}
PACK={"state":"PASS","code":"SOURCE_PACK_AND_PROCESS_RECONCILED",
      "process_lines":SOURCE}
PREPARED={"status":"READY","price_fields":{"Quote Net KRW":1955000},
          "sourcePackEvidence":PACK}

class EditProbeTests(unittest.TestCase):
    def test_mapping_prices_cloud_qty_and_pack_are_exact(self):
        r=audit_controls_snapshot(SOURCE,OBSERVED,HEADER,FLAGS)
        self.assertEqual(r["status"],"PASS")
        self.assertEqual(r["checks"]["source_unit_price_controls"],"PASS")
        self.assertEqual(r["checks"]["source_cloud_qty_control"],"PASS")
        self.assertEqual(r["new_quote_process_writer"],"NOT_VERIFIED")
        self.assertFalse(r["save_permitted"])
    def test_wrong_customer_unit_price_refused(self):
        changed=[dict(x) for x in OBSERVED]
        changed[0]["unitPriceKrw"]=135000
        with self.assertRaisesRegex(ValueError,"SOURCE_EDIT_UNIT_RATE_MISMATCH"):
            audit_controls_snapshot(SOURCE,changed,HEADER,FLAGS)
    def test_pack_change_and_duplicate_process_refused(self):
        changed=[dict(x) for x in OBSERVED]
        changed[1]["packNo"]="Package2"
        with self.assertRaisesRegex(ValueError,"SOURCE_EDIT_PROCESS_NOT_FOUND"):
            audit_controls_snapshot(SOURCE,changed,HEADER,FLAGS)
        with self.assertRaisesRegex(ValueError,"SOURCE_EDIT_PROCESS_IDENTITY_AMBIGUOUS"):
            audit_controls_snapshot(SOURCE,[OBSERVED[0],OBSERVED[0],OBSERVED[2]],HEADER,FLAGS)
    def test_missing_price_cloud_controls_and_cancel_refused(self):
        changed=[dict(x) for x in OBSERVED];changed[0]["price_editable"]=False
        with self.assertRaisesRegex(ValueError,"SOURCE_PRICE_FIELD_NOT_EDITABLE"):
            audit_controls_snapshot(SOURCE,changed,HEADER,FLAGS)
        changed=[dict(x) for x in OBSERVED];changed[2]["qty_editable"]=False
        with self.assertRaisesRegex(ValueError,"SOURCE_CLOUD_OR_SAMPLE_QTY_CONTROL_INVALID"):
            audit_controls_snapshot(SOURCE,changed,HEADER,FLAGS)
        with self.assertRaisesRegex(ValueError,"SOURCE_PACK_OR_CANCEL_CONTROLS_NOT_UNIQUE"):
            audit_controls_snapshot(SOURCE,OBSERVED,HEADER,{**FLAGS,"cancel_button":0})
    def test_source_probe_is_hold_even_after_live_source_controls_pass(self):
        verified=audit_controls_snapshot(SOURCE,OBSERVED,HEADER,FLAGS)
        verified["checks"]["source_cancel"]="PASS"
        verified["checks"]["source_original_unchanged"]="PASS"
        with patch("sfdc_pair_web_preview.prepare_pair",return_value=PREPARED):
            with patch("sfdc_pair_web_preview.run_source_control_probe",return_value=verified) as probe:
                r=run(FORM)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["code"],"SOURCE_EDIT_PROBE_PASS_NEW_QUOTE_WRITER_NOT_VERIFIED")
        self.assertEqual(r["readiness"]["source_edit_controls"],"PASS")
        self.assertEqual(r["readiness"]["quote_writer"],"UNVERIFIED")
        self.assertFalse(r["salesforce_write"]);self.assertFalse(r["save_permitted"])
        self.assertEqual(probe.call_args.args[0],QUOTE)
    def test_fail_closed_on_missing_pack_or_live_probe_exception(self):
        with patch("sfdc_pair_web_preview.prepare_pair",return_value={
           **PREPARED,"sourcePackEvidence":{"state":"BLOCK","code":"SOURCE_PACK_MISSING"}}):
            with patch("sfdc_pair_web_preview.run_source_control_probe") as probe:
                r=run(FORM)
            self.assertEqual(r["status"],"HOLD")
            self.assertEqual(r["code"],"SOURCE_PACK_MISSING")
            probe.assert_not_called()
        with patch("sfdc_pair_web_preview.prepare_pair",return_value=PREPARED):
            with patch("sfdc_pair_web_preview.run_source_control_probe",
                       side_effect=ValueError("SOURCE_PRICE_CHANGED_AFTER_CANCEL")):
                r=run(FORM)
            self.assertEqual(r["status"],"HOLD")
            self.assertEqual(r["code"],"SOURCE_PRICE_CHANGED_AFTER_CANCEL")
            self.assertEqual(r["readiness"]["source_edit_controls"],"HOLD")
            self.assertFalse(r["save_permitted"])
    def test_create_and_save_rejected_even_after_probe(self):
        for mode in ["SAVE","CREATE","COMMIT","CREATE_PAIR"]:
            with patch("sfdc_pair_web_preview.prepare_pair") as prepare:
                r=run({**FORM,"mode":mode})
            self.assertEqual(r["status"],"BLOCK")
            prepare.assert_not_called()
if __name__=="__main__":unittest.main()
