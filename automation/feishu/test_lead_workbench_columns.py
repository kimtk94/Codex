#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lead_workbench_columns as mod

class WorkbenchColumnTests(unittest.TestCase):
    def fields(self):
        names = list(mod.VISIBLE) + [
            "생성 후 발송 횟수", "생성 전 발송 횟수",
            "메일 증거 Message-ID", "메일 수신 유형",
            "메일 원본 확인시각", "Feishu 반영시각",
            "Lead 연락 대상 (자동)"
        ]
        return [{"field_name": name, "field_id": "fld"+str(i),
                 "type": 7 if name in ("재연락 필요", "메일 발송 예정", "검토 완료")
                 else 3 if name in ("Lead Status", "Description 있음", "연락 구분", "처리 방향")
                 else 1}
                for i,name in enumerate(names)]

    def test_hidden_fields_are_only_unnecessary_columns(self):
        fields = self.fields()
        expected = mod.make_plan(fields)
        self.assertEqual(len(expected), 7)
        self.assertNotIn("fld0", expected)
        self.assertNotIn("fld10", expected)
        self.assertIn("fld17", expected)
        self.assertEqual(mod.verify_hidden({"property": {"hidden_fields":expected}},expected),7)

    def test_missing_critical_field_blocks(self):
        fields=self.fields()
        fields=[x for x in fields if x["field_name"]!="Email"]
        with self.assertRaisesRegex(RuntimeError, "VISIBLE_REQUIRED_MISSING"):
            mod.make_plan(fields)

    def test_manual_checkboxes_immutable_schema(self):
        fields=self.fields()
        next(x for x in fields if x["field_name"]=="검토 완료")["type"]=1
        with self.assertRaisesRegex(RuntimeError, "MANUAL_SCHEMA_WRONG"):
            mod.make_plan(fields)

    def test_readback_mismatch_blocks(self):
        with self.assertRaisesRegex(RuntimeError, "HIDDEN_READBACK_MISMATCH"):
            mod.verify_hidden({"property":{"hidden_fields":["a"]}},["a","b"])
if __name__=="__main__":
    unittest.main()
