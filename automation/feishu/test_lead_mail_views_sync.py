#!/usr/bin/env python3
"""Offline safety regressions for isolated Feishu Lead view management."""
import sys
import unittest
import datetime as dt
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lead_mail_views_sync as v

def row(key, desc, contact="메일 발송 증거 없음"):
    return {
        "Lead ID": key, "고객명": "고객", "Account (고객 입력 원문)": "기관 원문",
        "Email": "test@example.com", "Lead Created": "2026-11-01",
        "Lead Status": "Open", "Description": "문의" if desc == "있음" else "",
        "Description 있음": desc,
        "내 메일 연락 여부": "미확인" if contact == "메일 발송 증거 없음" else "발송 확인",
        "연락 구분": contact, "생성 후 발송 횟수": "0",
        "생성 전 발송 횟수": "0", "최근 발송일": "",
        "메일 증거 Message-ID": "", "메일 수신 유형": "",
        "처리 방향": "검토", "메일 원본 확인시각": "2026-11-20T16:39:00+09:00",
    }

class ViewTests(unittest.TestCase):
    def setUp(self):
        patcher=mock.patch.object(v.age,"today_kst",return_value=dt.date(2026,11,21))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exact_four_email_evidence_views(self):
        self.assertEqual(len(v.VIEWS),4)
        self.assertEqual([x[2] for x in v.VIEWS],["있음","없음",None,None])
        self.assertEqual([x[1] for x in v.VIEWS],
                         [v.MAIL_CLASS,v.MAIL_CLASS,v.AFTER_CLASS,v.BEFORE_CLASS])

    def test_email_only_split(self):
        source={
            "a":row("a","있음"),
            "b":row("b","없음"),
            "c":row("c","있음","발송 확인 (Lead 생성 후)"),
        }
        self.assertEqual(v.expected_ids(source,"있음"),{"a"})
        self.assertEqual(v.expected_ids(source,"없음"),{"b"})

    def test_sent_after_and_before_are_separate_age_filtered_views(self):
        recent_after=row("sent1","있음","발송 확인 (Lead 생성 후)")
        recent_before=row("sent2","없음","Lead 생성 전만 발송")
        recent_after2=row("sent3","없음","발송 확인 (Lead 생성 후)")
        too_old=row("old","있음","발송 확인 (Lead 생성 후)")
        too_old["Lead Created"]="2025-11-20"
        boundary=row("boundary","없음","Lead 생성 전만 발송")
        boundary["Lead Created"]="2025-11-21"
        items={r["Lead ID"]:r for r in
               (recent_after,recent_before,recent_after2,too_old,boundary)}
        self.assertEqual(v.expected_ids(items,None,v.AFTER_CLASS),{"sent1","sent3"})
        self.assertEqual(v.expected_ids(items,None,v.BEFORE_CLASS),{"sent2","boundary"})
        self.assertEqual(v.expected_ids(items,"있음",v.AFTER_CLASS),{"sent1"})
        self.assertEqual(set(items),{"sent1","sent2","sent3","old","boundary"})

    def test_sent_views_do_not_filter_description_and_match_exact_mail_kind(self):
        fields={"연락 구분":"fldMail","Description 있음":"fldDesc",
                v.age.ELIGIBILITY_FIELD:"fldEligible"}
        for kind in (v.AFTER_CLASS,v.BEFORE_CLASS):
            expected=v.filter_definition(fields,None,kind)
            self.assertEqual(len(expected["conditions"]),2)
            self.assertEqual({x["field_id"] for x in expected["conditions"]},
                             {"fldMail","fldEligible"})
            self.assertTrue(v.filter_matches(expected,expected))
            self.assertFalse(v.filter_matches(expected,
                             v.filter_definition(fields,"있음",kind)))
        self.assertFalse(v.filter_matches(v.filter_definition(fields,None,v.AFTER_CLASS),
                         v.filter_definition(fields,None,v.BEFORE_CLASS)))

    def test_filter_requires_all_three_conditions(self):
        fields={"연락 구분":"fldMail","Description 있음":"fldDesc",v.age.ELIGIBILITY_FIELD:"fldEligible"}
        needed=v.filter_definition(fields,"있음")
        self.assertTrue(v.filter_matches(needed,needed))
        self.assertEqual(needed["conjunction"],"and")
        self.assertFalse(v.filter_matches({"conjunction":"or","conditions":needed["conditions"]},needed))
        self.assertFalse(v.filter_matches({"conjunction":"and","conditions":needed["conditions"][:1]},needed))
        self.assertFalse(v.filter_matches({"conjunction":"and","conditions":[
          dict(needed["conditions"][0],value='["발송 확인 (Lead 생성 후)"]'), needed["conditions"][1]]},needed))

    def test_parity_requires_exact_keys_and_values(self):
        source={str(i):row(str(i),"있음") for i in range(450)}
        observed={key:dict(value) for key,value in source.items()}
        counts=v.check_parity(source,observed)
        self.assertEqual(counts[("메일 발송 증거 없음","있음")],450)
        observed.pop("1")
        with self.assertRaisesRegex(RuntimeError,"ROW_COUNT"):
            v.check_parity(source,observed)
        observed["1"]=row("1","없음")
        with self.assertRaisesRegex(RuntimeError,"VALUE_MISMATCH"):
            v.check_parity(source,observed)

    def test_old_leads_removed_from_both_desc_views_without_deletion(self):
        old_present=row("old_yes","있음")
        old_present["Lead Created"]="2025-11-20"
        old_missing=row("old_no","없음")
        old_missing["Lead Created"]="2024-11-21"
        boundary=row("boundary","없음")
        boundary["Lead Created"]="2025-11-21"
        source={"old_yes":old_present,"old_no":old_missing,"boundary":boundary}
        self.assertEqual(v.expected_ids(source,"있음"),set())
        self.assertEqual(v.expected_ids(source,"없음"),{"boundary"})
        self.assertEqual(set(source),{"old_yes","old_no","boundary"})

    def test_no_contact_extrapolation(self):
        source={"a":row("a","있음", "Lead 생성 전만 발송")}
        self.assertEqual(v.expected_ids(source,"있음"),set())

if __name__=="__main__":
    unittest.main()
