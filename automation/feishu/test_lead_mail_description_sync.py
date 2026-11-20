#!/usr/bin/env python3
"""Offline regression for isolated Lead mail + Description Feishu sink."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lead_mail_description_sync as sync

class LeadMirrorTests(unittest.TestCase):
    def row(self, **values):
        sample={
            "Lead ID": "00Q-test", "Customer": "홍길동",
            "Institution": "고객이 입력한 기관명 그대로",
            "Email": "person@example.org", "Created Date": "2026-11-01",
            "Lead Status": "Open", "Description": "문의 원문 보존",
            "Description Class": "PRESENT", "My Mail Status": "SENT_AFTER_LEAD_CONFIRMED",
            "My Sent After Lead": "1", "My Sent Before Lead": "0",
            "Last Sent Ever": "2026-11-19T12:00:00+09:00",
            "QQ Message-ID (Evidence)": "msg-1", "To / CC": "TO",
            "Follow-up Action": "ALREADY_CONTACTED",
            "Latest QQ Outbound Checked": "2026-11-20T16:00:00+09:00",
        }
        sample.update(values)
        return [sample.get(field, "") for field in sync.SOURCE]
    def batch(self, rows):
        # The source count guard protects live writes. Use 450 distinct IDs.
        data = [self.row(**{"Lead ID": "00Q-%04d" % i}) for i in range(450)]
        data[:len(rows)] = rows
        return sync.transform(sync.SOURCE, data)
    def test_description_and_institution_are_not_normalized(self):
        items = self.batch([self.row()])
        r=items["00Q-test"]
        self.assertEqual(r["Account (고객 입력 원문)"], "고객이 입력한 기관명 그대로")
        self.assertEqual(r["Description"], "문의 원문 보존")
        self.assertEqual(r["내 메일 연락 여부"], "발송 확인")
    def test_no_mail_evidence_is_not_contact_confirmed(self):
        r=self.batch([self.row(**{
            "Description": "", "Description Class": "MISSING",
            "My Mail Status": "NO_PERSONAL_OUTBOUND_EVIDENCE",
            "My Sent After Lead": "0", "My Sent Before Lead": "0",
        })])["00Q-test"]
        self.assertEqual(r["내 메일 연락 여부"], "미확인")
        self.assertEqual(r["Description 있음"], "없음")
        self.assertIn("공통 안내", r["처리 방향"])
    def test_mail_before_lead_is_not_after_lead_contact(self):
        r=self.batch([self.row(**{
            "My Mail Status": "SENT_BEFORE_LEAD_ONLY",
            "My Sent After Lead": "0", "My Sent Before Lead": "2",
        })])["00Q-test"]
        self.assertEqual(r["내 메일 연락 여부"], "미확인")
        self.assertIn("생성 전만", r["연락 구분"])
    def test_mismatched_mail_counts_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "MAIL_STATUS_COUNT_CONFLICT"):
            self.batch([self.row(**{"My Sent After Lead":"0"})])
    def test_duplicate_ids_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE_LEAD_ID"):
            sync.transform(sync.SOURCE,[self.row(),self.row()])
    def test_schema_mismatch_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"LEAD_SOURCE_SCHEMA_MISSING"):
            sync.transform(["Lead ID"], [])
if __name__ == "__main__":
    unittest.main()
