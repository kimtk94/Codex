#!/usr/bin/env python3
"""Original H eTax document shared across ERP lines; sum F gross once per line."""
import unittest
import etax_grouped_manual_invoice_audit as m


def fixture(gross_a="1287000",gross_b="9317000",sales="Kim Taehoon",
            extra_certificate_member=False,cancel=""):
    number="20261022-123456789012345678901234"
    docs=[
        ["ERP Invoice Number",None,None,None,"E tax number"],
        ["20910000208",None,None,None,number],
        ["20910000209",None,None,None,number],
    ]
    if extra_certificate_member:
        docs.append(["20910000210",None,None,None,number])
    originals={}
    for erp,amount in (("20910000208",gross_a),("20910000209",gross_b)):
        row=[""]*10
        row[2]="46317"  # Oct 22 2026, CMS invoice date hint
        row[3]=erp
        row[5]=amount
        row[6]=sales
        row[7]=number
        row[8]="E tax issued"
        row[9]=cancel if erp=="20910000209" else ""
        originals[erp]=row
    return originals,docs


class GroupedOriginalEvidenceTests(unittest.TestCase):
    def test_one_etax_certificate_with_two_erp_lines_is_one_group(self):
        details,docs=fixture()
        report=m.evidence(details,docs)
        self.assertTrue(report["same_certificate"])
        self.assertEqual(report["certificate_group_member_count"],2)
        self.assertTrue(report["certificate_group_exact_pair"])
        self.assertEqual(report["gross_sum"],10604000)
        self.assertEqual(report["net_sum"],9640000)
        self.assertTrue(report["document_proof_consistent"])
        self.assertEqual(report["cms_month_hints"],["2026-10"])
        self.assertTrue(report["source_sales_matches_user"])

    def test_additional_erp_using_same_tax_number_requires_manual_review(self):
        details,docs=fixture(extra_certificate_member=True)
        report=m.evidence(details,docs)
        self.assertEqual(report["certificate_group_member_count"],3)
        self.assertFalse(report["certificate_group_exact_pair"])
        self.assertFalse(report["document_proof_consistent"])

    def test_cancel_number_or_mismatched_f_is_not_recognized(self):
        details,docs=fixture(cancel="2026-REFUND-TAX-NUMBER")
        report=m.evidence(details,docs)
        self.assertFalse(report["no_cancel"])
        self.assertFalse(report["document_proof_consistent"])
        details,docs=fixture(gross_b="10604000")
        report=m.evidence(details,docs)
        self.assertFalse(report["f_amounts_match"])
        self.assertFalse(report["total_matches"])
        self.assertFalse(report["document_proof_consistent"])

    def test_original_sales_label_does_not_equal_verified_owner(self):
        details,docs=fixture(sales="Other Representative")
        report=m.evidence(details,docs)
        self.assertTrue(report["same_sales_label"])
        self.assertFalse(report["source_sales_matches_user"])
        self.assertTrue(report["document_proof_consistent"])
        # Even a valid tax number and gross do not authorize personal revenue.

    def test_invalid_source_row_does_not_silently_match(self):
        details,docs=fixture()
        details["20910000209"][3]="20910000208"
        with self.assertRaisesRegex(RuntimeError,"ROW_IDENTITY_WRONG"):
            m.evidence(details,docs)

    def test_sales_alias_may_have_bilingual_suffix_without_exact_match(self):
        label="Kim Taehoon 김태훈"
        self.assertEqual(m.sales_hint(label),"DIFFERENT_OR_FORMAT_UNVERIFIED")
        clues=m.sales_token_clues(label)
        self.assertTrue(clues["has_kim"])
        self.assertTrue(clues["has_taehoon"])
        self.assertTrue(clues["has_full_alias"])
        self.assertFalse(m.sales_token_clues("Other Representative")["has_full_alias"])

    def test_exact_certificate_prefix_date_is_a_hint_not_issued_posting(self):
        self.assertEqual(m.date_hint("46317"),"20261022")
        self.assertEqual(m.date_hint("2026-10-22"),"20261022")
        self.assertEqual(m.date_hint("2026/10/22"),"20261022")
        self.assertEqual(m.date_hint("2026-13-22"),"UNKNOWN")
        rows,docs=fixture()
        result=m.evidence(rows,docs)
        self.assertTrue(all(x["cert_prefix_date_matches_C"]
                            for x in result["details"].values()))

    def test_date_hint_is_not_pretended_to_be_etax_issuance(self):
        self.assertEqual(m.month_hint("46317"),"2026-10")
        self.assertEqual(m.month_hint("2026-10-22"),"2026-10")
        self.assertEqual(m.month_hint("2026/10/22"),"2026-10")
        self.assertEqual(m.month_hint(""),"UNKNOWN")


if __name__=="__main__":
    unittest.main()
