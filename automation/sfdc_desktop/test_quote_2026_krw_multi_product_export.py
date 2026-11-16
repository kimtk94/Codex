"""Synthetic data only: exact per-Product source and price matching gates."""
import unittest
from decimal import Decimal
from quote_2026_krw_multi_product_export import (
    row_key,verify_multiset,verify_product_partitions,product_fingerprint,normalize_size,normalize_qty,
    extract_multi,
)

class NoNavigation:
    def goto(self,*args,**kwargs):
        raise AssertionError("MUST_NOT_NAVIGATE_UNVERIFIED_REFERENCE")

class MultiProductKrwTests(unittest.TestCase):
    def setUp(self):
        self.rows=[
            dict(quotation_product_id="QD-100001",process_name="Sequencing by lane",
                 process_id="Process-2020-04-29-00011",sample_quantity="2.00",data_size="1",data_unit="Lane"),
            dict(quotation_product_id="QD-100002",process_name="Sequencing by lane",
                 process_id="Process-2020-04-29-00011",sample_quantity="1.00",data_size="1",data_unit="Lane"),
            dict(quotation_product_id="QD-100002",process_name="Data release",
                 process_id="Process-2020-04-29-00077",sample_quantity="1",data_size="",data_unit=""),
        ]
        self.actual=[
            dict(process_name="Sequencing by lane",process_id="Process-2020-04-29-00011",
                 sample_quantity=2,data_size="1",data_unit="Lane"),
            dict(process_name="Sequencing by lane",process_id="Process-2020-04-29-00011",
                 sample_quantity=1,data_size="1",data_unit="Lane"),
            dict(process_name="Data release",process_id="Process-2020-04-29-00077",
                 sample_quantity=1,data_size="",data_unit="NA"),
        ]

    def test_multi_product_qq_report_process_multiset_exact(self):
        self.assertTrue(verify_multiset(self.rows,self.actual))
        self.assertEqual(row_key("Sequencing by lane","2.00","1.0","Lane"),
                         row_key("Sequencing by lane",2,"1","Lane"))

    def test_reject_wrong_price_row_quantity_unit_or_missing_product(self):
        for changes in [
            {"sample_quantity":3},{"data_size":"2"},{"data_unit":"Gb"},
            {"process_name":"Other"}]:
            actual=[dict(x) for x in self.actual]
            actual[0].update(changes)
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,"SOURCE_PROCESS_MULTISET_MISMATCH"):
                verify_multiset(self.rows,actual)
        missing=[dict(x) for x in self.rows]
        missing[0]["quotation_product_id"]=""
        with self.assertRaisesRegex(ValueError,"SOURCE_QUOTE_PRODUCT_ID_UNVERIFIED"):
            verify_multiset(missing,self.actual)

    def test_exact_qq_qd_partition_to_article_mapping(self):
        self.assertTrue(verify_product_partitions(
            self.rows,[self.actual[:1],self.actual[1:]]))
        # Salesforce articles can render in a different order from the QQ report.
        self.assertTrue(verify_product_partitions(
            self.rows,[self.actual[1:],self.actual[:1]]))

    def test_aggregate_match_does_not_allow_product_process_mixing(self):
        shifted=[[self.actual[0],self.actual[2]],[self.actual[1]]]
        # The Quote-wide process multiset still passes; Product ownership differs.
        self.assertTrue(verify_multiset(self.rows,[r for group in shifted for r in group]))
        with self.assertRaisesRegex(ValueError,"SOURCE_PRODUCT_PARTITION_MISMATCH"):
            verify_product_partitions(self.rows,shifted)
        with self.assertRaisesRegex(ValueError,"SOURCE_PRODUCT_PARTITION_MISMATCH"):
            verify_product_partitions(self.rows,[self.actual])
        with self.assertRaisesRegex(ValueError,"EMPTY_PRODUCT_ARTICLE"):
            verify_product_partitions(self.rows,[[],self.actual])

    def test_different_article_codes_create_different_product_signatures(self):
        rows=[dict(process_id="Process-2020-04-29-00011",process_type="NovaSeq X Plus (PE150)",
                   unit_price_krw="200000",line_total_krw="400000")]
        a=product_fingerprint("RSSQ01203",rows)
        b=product_fingerprint("RSSQ01503",rows)
        self.assertNotEqual(a,b)
        self.assertEqual(len(a),64)

    def test_invalid_quote_or_approval_blocks_before_navigation(self):
        base={"quote_id":"QID-2026-11-02-411018","record_id":"a0P000000000AAA",
              "created_date":"2026-11-02","approval_evidence":"APPROVED_TEXT",
              "expected_process_lines":self.rows}
        for change in [{"approval_evidence":"PENDING"},{"created_date":"2025-11-02"},
                       {"created_date":"2026-11-03"},{"expected_process_lines":[]}]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                extract_multi(NoNavigation(),{**base,**change})

    def test_native_amounts_and_missing_unit_never_infer_gb(self):
        self.assertEqual(normalize_size("6.000"),"6")
        self.assertEqual(normalize_size(""),"")
        self.assertEqual(normalize_qty("15.00"),15)
        with self.assertRaises(ValueError):normalize_size("-1")
        with self.assertRaises(ValueError):normalize_qty("0")
        self.assertEqual(Decimal("9400000")*Decimal("1.10"),Decimal("10340000.00"))

if __name__=="__main__":
    unittest.main()
