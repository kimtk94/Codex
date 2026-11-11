#!/usr/bin/env python3
import unittest
import quote_dashboard_preview as p
from qq_mail_ingest import SafeError
LINK="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tblabc&view=vewxyz"
def record(key,week,checked=False,status="INCLUDED"):
    return {"fields":{"Source Key":"QUOTE_REVIEW:"+key,"Chart Window":"RECENT_4_PLUS_CURRENT",
      "Quote Name":"Test Quote","기관":"Test Institute","서비스·공정":"mRNA",
      "샘플수(공정별)":"4","참고 견적 USD":"1000","합산 제외":checked,
      "합산 상태":status,"SFDC IsActive":"1","Week Start":week,
      "Approval KST":week+" 10:00:00"}}
class PreviewTests(unittest.TestCase):
    def test_verified_rows_and_link(self):
        rows=p.extract([record("a0P"+"A"*12,"2026-11-06"),
                        record("a0P"+"B"*12,"2026-10-30",True,"NOT_INCLUDED")])
        text=p.render(rows,LINK)
        for term in ("읽기 전용","수정하려면","WEEKLY_TREND","Weekly Quote 편집",
                     "합산 제외","승인 1건","합산 1건","체크 제외 1건"):
            self.assertIn(term,text)
        for fake_control in ("☐","☑","| 제외 |","[견적 목록 열기"):
            self.assertNotIn(fake_control,text)
    def test_bad_source_rejected(self):
        row=record("a0P"+"A"*12,"2026-11-06")
        with self.assertRaisesRegex(SafeError,"DUPLICATE"):
            p.extract([row,row])
        with self.assertRaisesRegex(SafeError,"INVALID_EDITABLE_LINK"):
            p.render([("2026-11-06","", "k",row["fields"])],"https://example.net")
if __name__=="__main__":
    unittest.main()
