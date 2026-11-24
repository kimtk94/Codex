#!/usr/bin/env python3
"""Offline, synthetic-only regression tests for read-only Invoice parity triage."""
import json
import unittest

from automation.css_mail import qq_invoice_parity_audit as audit


class InvoiceGapTriageTests(unittest.TestCase):
    def setUp(self):
        self.old_year = audit.YEAR
        audit.YEAR = "2026"

    def tearDown(self):
        audit.YEAR = self.old_year

    @staticmethod
    def qq(number, month, amount=1000, evidence="FILENAME_PARSED"):
        return {"invoice_number": number, "issued_month": month,
                "amount_krw": str(amount), "evidence": evidence}

    @staticmethod
    def css(number, month, amount=1000):
        return {"invoice_number": number, "invoice_month": month,
                "amount_krw": str(amount)}

    @staticmethod
    def extracted(number, amount=1000, status="FILENAME_PARSED"):
        return {"invoice_number": number, "amount_krw": str(amount),
                "validation_status": status}

    def test_reconciles_month_and_extract_without_identifiers(self):
        evidence = [self.qq("1111111111", "2026-09"),
                    self.qq("2222222222", "2026-10"),
                    self.qq("3333333333", "2026-11"),
                    self.qq("4444444444", "2025-12")]
        canonical = [self.css("1111111111", "2026-09")]
        extracted = [self.extracted("2222222222")]
        result, failed = audit.summarize(evidence, canonical, extracted)
        self.assertTrue(failed)
        self.assertEqual(result["qq_evidence"], 3)
        self.assertEqual(result["missing_in_css"], 2)
        self.assertEqual(result["missing_in_css_by_month"],
                         {"2026-10": 1, "2026-11": 1})
        self.assertEqual(result["qq_latest_invoice_month"], "2026-11")
        self.assertEqual(result["css_latest_invoice_month"], "2026-09")
        self.assertEqual(result["extract_crosscheck"]["found"], 1)
        self.assertEqual(result["extract_crosscheck"]["amount_matches"], 1)
        self.assertEqual(result["extract_crosscheck"]["not_found"], 1)
        self.assertNotIn("2222222222", json.dumps(result))
        self.assertNotIn("3333333333", json.dumps(result))
        self.assertNotIn("examples", result)

    def test_matching_source_passes(self):
        record = self.qq("1111111111", "2026-10")
        result, failed = audit.summarize([record],
                                        [self.css("1111111111", "2026-10")], [])
        self.assertFalse(failed)
        self.assertEqual(result["missing_in_css"], 0)

    def test_different_amount_in_originals_fails(self):
        result, failed = audit.summarize(
            [self.qq("1111111111", "2026-10", amount=1000)],
            [self.css("1111111111", "2026-10", amount=900)], [])
        self.assertTrue(failed)
        self.assertEqual(result["amount_mismatch"], 1)

    def test_extracted_conflict_not_considered_corroboration(self):
        result, failed = audit.summarize([self.qq("1111111111", "2026-11")],
                                         [self.css("2222222222", "2026-11")],
                                         [self.extracted("1111111111", amount=900)])
        self.assertTrue(failed)
        self.assertEqual(result["extract_crosscheck"]["amount_conflicts"], 1)

    def test_duplicated_extracted_invoice_is_held(self):
        result, failed = audit.summarize(
            [self.qq("1111111111", "2026-11")],
            [self.css("2222222222", "2026-11")],
            [self.extracted("1111111111"), self.extracted("1111111111")])
        self.assertTrue(failed)
        self.assertEqual(result["extract_crosscheck"]["duplicate_numbers"], 1)

    def test_empty_sources_fail_closed(self):
        result, failed = audit.summarize([], [], [])
        self.assertTrue(failed)
        self.assertEqual(result["qq_evidence"], 0)

    def test_invalid_invoice_id_never_leaks_suffix(self):
        with self.assertRaisesRegex(ValueError, "^INVALID_INVOICE_NUMBER$"):
            audit.summarize([self.qq("SENSITIVE1234", "2026-11")], [], [])


    def test_all_four_lineage_keys_crosschecked_before_promotion(self):
        source=self.qq("1111111111", "2026-11")
        source.update({"amea_project_id":"AMEA-TEST", "h_project_id":"H-TEST",
                       "po_reference":"PO-TEST", "imap_uid":"100"})
        extracted=self.extracted("1111111111")
        extracted.update({"project_id":"AMEA-TEST","h_project_number":"H-TEST",
                          "po_reference":"PO-TEST", "imap_uid":"100"})
        result, failed=audit.summarize([source],
                                       [self.css("2222222222", "2026-11")],
                                       [extracted])
        self.assertTrue(failed)
        self.assertEqual(result["extract_crosscheck"]["all_four_lineage_fields_matching"],1)
        self.assertEqual(result["extract_crosscheck"]["identity_fields_conflicting"],{})
        self.assertFalse(result["extract_crosscheck"]["original_mail_verified"])

    def test_matching_amount_but_conflicting_uid_stays_hold(self):
        source=self.qq("1111111111", "2026-11")
        source.update({"amea_project_id":"AMEA-TEST", "h_project_id":"H-TEST",
                       "po_reference":"PO-TEST", "imap_uid":"100"})
        extracted=self.extracted("1111111111")
        extracted.update({"project_id":"AMEA-TEST","h_project_number":"H-TEST",
                          "po_reference":"PO-TEST", "imap_uid":"200"})
        result, failed=audit.summarize([source],
                                       [self.css("2222222222", "2026-11")],
                                       [extracted])
        self.assertTrue(failed)
        self.assertEqual(result["extract_crosscheck"]["amount_matches"],1)
        self.assertEqual(result["extract_crosscheck"]["identity_fields_conflicting"],{"imap_uid":1})
        self.assertEqual(result["extract_crosscheck"]["all_four_lineage_fields_matching"],0)


if __name__ == "__main__":
    unittest.main()
