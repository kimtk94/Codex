#!/usr/bin/env python3
"""Offline reconciliation tests for chained Lead mail-to-Feishu automation."""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import lead_outreach_pipeline_evidence as p

NOW=dt.datetime(2026,11,21,3,0,tzinfo=dt.timezone.utc)
DATE="2026-11-20T15:21:09+00:00"
STATES={"SENT_AFTER_LEAD_CONFIRMED":275,
        "SENT_BEFORE_LEAD_ONLY":39,
        "NO_PERSONAL_OUTBOUND_EVIDENCE":736}

def pack(prefix,dict_value):
    return prefix+json.dumps(dict_value,ensure_ascii=False)

def example():
    personal=(pack("PERSONAL_LEAD_AUDIT=",{
       "leads":1050,"states":STATES,"latest_qq":DATE})+
       "\nPERSONAL_LEAD_AUDIT_APPLIED_AND_VERIFIED=true")
    mirror=(pack("LEAD_MAIL_DESCRIPTION_PLAN=",{
        "total":1050,"existing":1050,"create":0,"update":0,
        "retained_not_deleted":0,"groups":{}})+
        "\nLEAD_MANUAL_SELECTION_PRESERVED=1050"+
        "\nFEISHU_LEAD_MAIL_DESCRIPTION_READBACK=PASS")
    queue=(pack("LEAD_QUEUE_PLAN=",{
        "total":1050,"changes":0,"queue_field_exists":True,
        "eligibility_field_exists":True,
        "groups":{"recontact":0,"planned":0,"review":423,
                  "none":209,"expired":418},
        "eligibility":{"cutoff":"2025-11-21","inclusive":True,
                       "counts":{"eligible":632,"expired":418}},
        "eligible_no_evidence":{"description_present":90,
                                "description_missing":334},
        "eligible_mail_status":{"after":174,"prior_only":34,"no_evidence":424},
        "mode":"APPLY"})+
        "\nLEAD_QUEUE_MANUAL_STATES_PRESERVED=1050"+
        "\nLEAD_QUEUE_READBACK_PASS=1 MODE=APPLY")
    views="\n".join([
        pack("LEAD_VIEW_VERIFIED=",{"view":"01 · 발송 증거 없음 · Description 있음",
                                   "count":90,"url":"redacted"}),
        pack("LEAD_VIEW_VERIFIED=",{"view":"02 · 발송 증거 없음 · Description 없음",
                                   "count":334,"url":"redacted"}),
        pack("LEAD_VIEW_VERIFIED=",{"view":"06 · 최근 1년 · Lead 생성 후 발송 확인",
                                   "count":174,"url":"redacted"}),
        pack("LEAD_VIEW_VERIFIED=",{"view":"07 · 최근 1년 · Lead 생성 전만 발송",
                                   "count":34,"url":"redacted"}),
        "LEAD_VIEW_AUDIT_PASS=1 MODE=APPLY",
        "LEAD_VIEW_COUNT_VERIFIED=4"])
    plan=pack("LEAD_DELTA_PLAN=",{
        "records":1050,"pending_updates":0,"allowed_max":262,
        "counts_before":{"recontact":0,"planned":0,"review":423,"none":209,"expired":418}})
    preview=plan+"\nLEAD_DELTA_READ_ONLY_PASS=1"
    applied=plan+"\n"+pack("LEAD_DELTA_NO_NEW_DATA=1 ",{
        "checked":1050,"views_verified":3,"writes":0,
        "second_snapshot_verified":True,
        "counts":{"recontact":0,"planned":0,"review":423,"none":209,"expired":418}})
    return [personal,mirror,queue,views,preview,applied]

class Tests(unittest.TestCase):
    def test_accepts_verified_pipeline_without_raw_mail(self):
        result=p.validate(*example(),now=NOW)
        self.assertEqual(result["result"],"PASS")
        self.assertEqual(result["lead_total"],1050)
        self.assertEqual(result["eligible"],632)
        self.assertEqual(result["excluded_over_one_year"],418)
        self.assertEqual(result["outreach_description_present"],90)
        self.assertEqual(result["outreach_description_missing"],334)
        self.assertEqual(result["recent_sent_after_lead"],174)
        self.assertEqual(result["recent_sent_before_lead_only"],34)
        self.assertEqual(result["sent_mail_views_verified"],2)
        self.assertEqual(result["final_delta"],"NO_NEW_DATA")
        self.assertFalse(result["mail_sent_by_automation"])
        self.assertFalse(result["pii_in_artifact"])

    def test_email_newly_sent_removes_from_outreach_view(self):
        sample=example()
        sample[0]=sample[0].replace('"SENT_AFTER_LEAD_CONFIRMED": 275',
                                    '"SENT_AFTER_LEAD_CONFIRMED": 276').replace(
                                    '"NO_PERSONAL_OUTBOUND_EVIDENCE": 736',
                                    '"NO_PERSONAL_OUTBOUND_EVIDENCE": 735')
        sample[2]=sample[2].replace('"description_present": 90',
                                    '"description_present": 89').replace(
                                    '"after": 174','"after": 175').replace(
                                    '"no_evidence": 424','"no_evidence": 423')
        sample[3]=sample[3].replace('"count": 90','"count": 89').replace(
                                    '"count": 174','"count": 175')
        result=p.validate(*sample,now=NOW)
        self.assertEqual(result["sent_after_lead"],276)
        self.assertEqual(result["outreach_description_present"],89)

    def test_rejects_missing_personal_source_verification(self):
        sample=example();sample[0]=sample[0].replace(
            "PERSONAL_LEAD_AUDIT_APPLIED_AND_VERIFIED=true","")
        with self.assertRaisesRegex(p.EvidenceError,"PERSONAL_MAIL_SOURCE"):
            p.validate(*sample,now=NOW)

    def test_rejects_mirror_manual_flags_not_verified(self):
        sample=example();sample[1]=sample[1].replace(
            "LEAD_MANUAL_SELECTION_PRESERVED=1050",
            "LEAD_MANUAL_SELECTION_PRESERVED=1049")
        with self.assertRaisesRegex(p.EvidenceError,"MANUAL_FLAGS"):
            p.validate(*sample,now=NOW)

    def test_rejects_expired_total_drift(self):
        sample=example();sample[2]=sample[2].replace(
            '"counts": {"eligible": 632, "expired": 418}',
            '"counts": {"eligible": 632, "expired": 417}')
        with self.assertRaisesRegex(p.EvidenceError,"ELIGIBILITY_TOTAL_MISMATCH"):
            p.validate(*sample,now=NOW)

    def test_rejects_view_id_or_count_drift(self):
        sample=example();sample[3]=sample[3].replace('"count": 334','"count": 335')
        with self.assertRaisesRegex(p.EvidenceError,"OUTREACH_VIEW_ELIGIBILITY_MISMATCH"):
            p.validate(*sample,now=NOW)

    def test_rejects_missing_sent_view_even_if_both_unsent_views_match(self):
        sample=example()
        sample[3]="\n".join(x for x in sample[3].splitlines()
            if "07 · 최근 1년 · Lead 생성 전만 발송" not in x)
        with self.assertRaisesRegex(p.EvidenceError,"OUTREACH_VIEW_ELIGIBILITY_MISMATCH"):
            p.validate(*sample,now=NOW)

    def test_rejects_sent_view_count_drift_and_eligible_partition(self):
        sample=example()
        sample[3]=sample[3].replace('"count": 174','"count": 175')
        with self.assertRaisesRegex(p.EvidenceError,"OUTREACH_VIEW_ELIGIBILITY_MISMATCH"):
            p.validate(*sample,now=NOW)
        sample=example()
        sample[2]=sample[2].replace('"after": 174','"after": 175')
        with self.assertRaisesRegex(p.EvidenceError,"ELIGIBLE_SENT_OUTBOUND_PARTITION_MISMATCH"):
            p.validate(*sample,now=NOW)

    def test_rejects_stale_mail_source(self):
        sample=example();sample[0]=sample[0].replace(DATE,"2026-11-17T01:00:00+00:00")
        with self.assertRaisesRegex(p.EvidenceError,"QQ_SOURCE_TIMESTAMP_STALE"):
            p.validate(*sample,now=NOW)

    def test_rejects_feishu_final_readback_failure(self):
        sample=example();sample[5]="LEAD_DELTA_FAILED=LEAD_DELTA_VIEW_IDS_MISMATCH"
        with self.assertRaisesRegex(p.EvidenceError,"FINAL_DELTA_READBACK_UNVERIFIED"):
            p.validate(*sample,now=NOW)

    def test_rejects_personal_status_sum_drift(self):
        sample=example();sample[0]=sample[0].replace('"NO_PERSONAL_OUTBOUND_EVIDENCE": 736',
                                                    '"NO_PERSONAL_OUTBOUND_EVIDENCE": 735')
        with self.assertRaisesRegex(p.EvidenceError,"PERSONAL_MAIL_STATUS_TOTAL_CONFLICT"):
            p.validate(*sample,now=NOW)

if __name__=="__main__":
    unittest.main()
