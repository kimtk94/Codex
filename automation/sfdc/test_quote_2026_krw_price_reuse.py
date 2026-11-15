"""Synthetic pricing rows only. No real customer identities, private prices or calls."""
import unittest
from quote_2026_krw_price_reuse import choose_price_references, _valid_reference, _date_to_iso

ACCOUNT_A = "001000000000AAA"
ACCOUNT_B = "001000000000AAB"
CONTACT_A = "003000000000AAA"
CONTACT_B = "003000000000AAB"
CONTACT_C = "003000000000AAC"
PRODUCT = "f"*64
PROC = "Process-2020-04-29-00031"

def record(quote="QID-2026-07-01-123456", account=ACCOUNT_A, contact=CONTACT_A, **changes):
    row = {
        "source_kind":"VERIFIED_SFDC_KRW_PROCESS_PRICE",
        "source_verified":True,
        "created_date":"2026-07-01",
        "quote_id":quote,
        "active":True,
        "approval_status":"APPROVED",
        "currency":"KRW",
        "was_usd_converted":False,
        "vat_basis":"VAT_EXCLUDED",
        "account_id":account,
        "contact_id":contact,
        "process_id":PROC,
        "product_signature":PRODUCT,
        "unit_price_krw":"200000",
        "data_unit":"G raw data",
        "data_size":"6",
        "sample_quantity":20,
    }
    row.update(changes)
    return row

REQUEST = {"account_id":ACCOUNT_A,"contact_id":CONTACT_A,
           "process_id":PROC,"product_signature":PRODUCT,
           "data_unit":"Gb","data_size":"6","sample_quantity":20}

class KrwReuseTests(unittest.TestCase):
    def test_2026_krw_approved_rank_same_customer_before_other_customer(self):
        cases=[
            record("QID-2026-07-01-123456",ACCOUNT_B,CONTACT_C),
            record("QID-2026-07-02-123457",ACCOUNT_A,CONTACT_B),
            record("QID-2026-07-03-123458",ACCOUNT_A,CONTACT_A),
        ]
        answer=choose_price_references(REQUEST,cases)
        self.assertEqual([c["tier"] for c in answer["candidates"]],
            ["SAME_ACCOUNT_CONTACT","SAME_ACCOUNT_OTHER_CONTACT","OTHER_CUSTOMER_SAME_PRODUCT_PROCESS"])
        self.assertFalse(answer["candidates"][0]["comparison_only"])
        self.assertTrue(answer["candidates"][1]["comparison_only"])
        self.assertFalse(answer["price_auto_apply"])
        self.assertEqual(answer["crm_writes"],0)

    def test_2025_usd_converted_unapproved_all_excluded(self):
        cases=[record(created_date="2025-12-31"),
               record(currency="USD"),
               record(was_usd_converted=True),
               record(approval_status="PENDING"),
               record(source_kind="SFDC_EMAIL_25COL_USD_ONLY"),
               record(source_verified=False),
               record(vat_basis="UNKNOWN")]
        r=choose_price_references(REQUEST,cases)
        self.assertEqual(r["candidates"],[])
        self.assertEqual(r["status"],"NO_2026_KRW_MATCH")
        self.assertEqual(r["rejections"]["OUTSIDE_2026"],1)
        self.assertEqual(r["rejections"]["NOT_NATIVE_KRW"],2)

    def test_external_cp_contact_and_unverified_account_rejected(self):
        results=choose_price_references(REQUEST,[
            record(contact_id="CP2026042900001"),
            record(account_id="not-native"),
            record(contact_id=""),
        ])
        self.assertEqual(len(results["candidates"]),0)
        self.assertEqual(results["rejections"]["CONTACT_003_UNVERIFIED"],2)
        self.assertEqual(results["rejections"]["ACCOUNT_ID_UNVERIFIED"],1)

    def test_same_account_other_quantity_requires_comparison_review(self):
        row=record(sample_quantity=48,data_size="12")
        res=choose_price_references(REQUEST,[row])
        self.assertEqual(res["candidates"][0]["tier"],"SAME_ACCOUNT_CONTACT")
        self.assertTrue(res["candidates"][0]["comparison_only"])
        self.assertFalse(res["candidates"][0]["size_match"])
        self.assertFalse(res["candidates"][0]["quantity_match"])

    def test_different_product_or_unit_no_price_suggestion(self):
        a=choose_price_references(REQUEST,[
            record(product_signature="b"*64),
            record(process_id="Process-2020-04-29-00032"),
            record(data_unit="M raw reads"),
        ])
        self.assertEqual(a["candidates"],[])
        self.assertEqual(a["rejections"]["OTHER_PRODUCT_PROCESS"],2)
        self.assertEqual(a["rejections"]["UNIT_MISMATCH"],1)

    def test_zero_price_is_valid_but_requires_approval(self):
        row=record(unit_price_krw="0")
        self.assertEqual(_valid_reference(row),"PASS")
        r=choose_price_references(REQUEST,[row])
        self.assertEqual(r["candidates"][0]["unit_price_krw"],"0")
        self.assertTrue(r["candidates"][0]["requires_record_approval"])

    def test_failed_request_blocks_without_scanning_history(self):
        bad={**REQUEST,"process_id":"invalid"}
        r=choose_price_references(bad,[record()])
        self.assertEqual(r["status"],"HOLD_PRODUCT_PROCESS_UNVERIFIED")
        self.assertEqual(r["candidates"],[])

    def test_parse_quote_dates_for_2026_report_audit(self):
        self.assertEqual(_date_to_iso("11/12/2026"),"2026-11-12")
        self.assertEqual(_date_to_iso("1/1/2025"),"2025-01-01")

if __name__=="__main__":
    unittest.main()
