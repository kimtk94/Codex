"""Synthetic regression for Salesforce source provenance gates; no CRM access."""
import datetime as dt
import unittest
from contact_lookup_source_gate import assess_source_gate, KST

NOW=dt.datetime(2026,11,6,8,0,tzinfo=KST)

def data(fresh="YES",ids="YES",timestamp="2026-11-06T06:00:00+09:00",links="True"):
    audit=[["source_tab","record_count","first_seen_this_snapshot","last_checked_kst","content_changed","fingerprint_sha256","source_kind","freshness_verified"]]
    ready=[["object","records","stable_id","modified_timestamp","required_field_check","missing_fields","promotion_status","source"]]
    for obj in ("SFDC Opportunity Raw","SFDC Contacts","Quotation"):
        audit.append([obj,"100","",timestamp,"NO","synthetic","SFDC_Auto snapshot",fresh])
        ready.append([obj,"100",ids,"YES","PASS","","review","SFDC_Auto snapshot"])
    link=[["metric","value"]]+[[key,links] for key in ("active_validation_ready","sfdc_quote_id_column_present","related_opportunity_id_column_present")]
    mail=[["report","sample"],["Metric","Pilot (legacy)","Latest QQ staged","Delta"],["Lead records","100","515","415"],["Opportunity records","100","706","606"],["Unique quotation IDs","100","837","737"]]
    return audit,ready,link,mail

class GateTests(unittest.TestCase):
    def eval(self,**kw):
        return assess_source_gate(*data(**kw),now=NOW)

    def test_valid_synthetic_source_still_no_web_connection(self):
        r=self.eval()
        self.assertEqual(r["contact_lookup_gate"],"READY_FOR_AUTHENTICATED_LIVE_RECHECK")
        self.assertEqual(r["opportunity_quote_gate"],"READY_FOR_AUTHENTICATED_LIVE_RECHECK")
        self.assertEqual(r["website_live_search"],"NOT_CONNECTED")
        self.assertFalse(r["writes_performed"])

    def test_recent_copy_without_proof_blocks(self):
        r=self.eval(fresh="NO")
        self.assertEqual(r["contact_lookup_gate"],"BLOCK")
        self.assertTrue(r["objects"]["SFDC Contacts"]["copy_checked_recently"])
        self.assertFalse(r["objects"]["SFDC Contacts"]["freshness_proven"])

    def test_missing_source_ids_blocks(self):
        self.assertEqual(self.eval(ids="NO")["contact_lookup_gate"],"BLOCK")

    def test_old_snapshot_blocks(self):
        self.assertEqual(self.eval(timestamp="2026-11-01T06:00:00+09:00")["contact_lookup_gate"],"BLOCK")

    def test_quote_link_only_blocks_quote_gate(self):
        r=self.eval(links="False")
        self.assertEqual(r["opportunity_quote_gate"],"BLOCK")
        self.assertEqual(r["contact_lookup_gate"],"READY_FOR_AUTHENTICATED_LIVE_RECHECK")

    def test_email_report_counts_cannot_authorize_contact_lookup(self):
        r=self.eval(fresh="NO")
        self.assertEqual(r["report_staging_only"],{"leads":515,"opportunities":706,"quotation_ids":837})
        self.assertEqual(r["contact_lookup_gate"],"BLOCK")

    def test_invalid_missing_field_blocks(self):
        args=list(data())
        args[1][2][5]="Account ID"
        r=assess_source_gate(*args,now=NOW)
        self.assertFalse(r["objects"]["SFDC Contacts"]["schema_pass"])
        self.assertEqual(r["contact_lookup_gate"],"BLOCK")

    def test_no_data_fails_closed(self):
        r=assess_source_gate([],[],[],[],now=NOW)
        self.assertEqual(r["opportunity_quote_gate"],"BLOCK")

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            assess_source_gate(*data(),now=dt.datetime(2026,11,6,8,0))
