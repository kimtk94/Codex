import unittest
from feishu_sfdc_bridge import FIELDS, QUEUE_COLUMNS, RESULT_COLUMNS, validate_request, pure_reconcile, field_specs

GOOD={"record_id":"rec123456789", "created_time":0,"fields":{
    "요청 ID":"SFDC-20261109-A001","기능":"Oppo + Quote", "요청":"PREFLIGHT",
    "원본 ID":"006000000000000AAA","원본 Quote ID":"a0P000000000000AAA",
    "새 이름":"Korea-Example-12-mRNA","기관":"예시대학교","담당 Contact":"가나다",
    "샘플 수":12,"샘플당 Gb":12,"마감일":"2026-11-30",
    "신규 Progress Description":"New 12 sample request, PO unconfirmed.",
    "가격 확인":False,"중복 확인":False,"실제 저장 승인":False}}
class TestBridge(unittest.TestCase):
    def test_schema_no_duplicates(self):
        self.assertEqual(len(FIELDS),len(set(k for k,v in FIELDS)))
        self.assertEqual(len(QUEUE_COLUMNS),18)
        self.assertEqual(len(RESULT_COLUMNS),11)
        self.assertEqual(field_specs()[0]["field_name"],"요청 ID")
    def test_valid_preflight(self):
        row=validate_request(GOOD)
        self.assertIsNotNone(row)
        self.assertEqual(row[3:5],["oppo_quote_pair","PREFLIGHT"])
        self.assertEqual(row[10:12],["12","12.0"])
    def test_save_requires_three_attestations(self):
        x={**GOOD,"fields":{**GOOD["fields"],"요청":"SAVE"}}
        self.assertIsNone(validate_request(x))
        x["fields"].update({"가격 확인":True,"중복 확인":True,"실제 저장 승인":True})
        row=validate_request(x)
        self.assertEqual(row[4],"SAVE")
    def test_bad_id_and_blank_progress_blocked(self):
        x={**GOOD,"fields":{**GOOD["fields"],"원본 ID":"009INVALID"}}
        self.assertIsNone(validate_request(x))
        x["fields"]["원본 ID"]="006000000000000AAA"
        x["fields"]["신규 Progress Description"]="copy"
        self.assertIsNone(validate_request(x))
    def test_reconcile_only_matching_hash(self):
        req=validate_request(GOOD)
        report=[req[0],req[1],req[2],"PREFLIGHT_PASS","", "2350000","235000", "","","2026-11-09T12:00:00Z","PREFLIGHT"]
        self.assertEqual(len(pure_reconcile([req],[report])),1)
        out=pure_reconcile([req],[report])[0]
        self.assertEqual(out["fields"]["예상 공급가 KRW"],2350000)
        report[2]="deadbeef"
        self.assertEqual(pure_reconcile([req],[report]),[])
    def test_cannot_inject_unauthorized_status(self):
        req=validate_request(GOOD)
        report=[req[0],req[1],req[2],"CREATED", "", "", "", "", "", "", ""]
        self.assertEqual(pure_reconcile([req],[report]),[])

if __name__=='__main__':unittest.main()
