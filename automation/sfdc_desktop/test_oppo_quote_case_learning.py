"""Synthetic Oppo/Quote naming cases; customer records never committed."""
import unittest

from oppo_quote_case_learning import (
    classify_case, normalize_mode, operational_depth_unit, summarize_case_pairs,
    validate_request_draft, modes_in_case
)


def valid_draft():
    return {
        "contact_email": "researcher@example.org",
        "service": "PMP",
        "sequencing_mode": "250PE",
        "sample_count": 5,
        "depth_per_sample": 1,
        "depth_unit": "M reads",
    }


class HistoricalQuoteTrainingTests(unittest.TestCase):
    def test_legacy_pe250_gb_is_review_not_policy(self):
        s = classify_case("Korea-SyntheticInstitute-5-PMP-PE250-4Gb")
        self.assertEqual(s["status"], "HISTORICAL_UNIT_CONFLICT_REVIEW")
        self.assertEqual(s["modes"], ["PE250"])
        self.assertEqual(operational_depth_unit("PE250"), "M reads")

    def test_current_pmp_250pe_mreads_aligned(self):
        s = classify_case("Korea-Institution-5-PMP-250PE-1M reads")
        self.assertEqual(s["status"], "CURRENT_POLICY_ALIGNED")
        self.assertTrue(s["pmp"])

    def test_standard_pe150_gb_aligned(self):
        s = classify_case("Korea-Institution-5-PMP-PE150-6Gb")
        self.assertEqual(s["status"], "CURRENT_POLICY_ALIGNED")

    def test_inconsistent_pe150_mreads_flagged(self):
        s = classify_case("Korea-Institution-5-PMP-PE150-10M reads")
        self.assertEqual(s["status"], "HISTORICAL_UNIT_CONFLICT_REVIEW")

    def test_mixed_service_multiple_depth_units_requires_review(self):
        s = classify_case("Korea-Institution-5-PMP-250PE-1M reads-Additional-10Gb")
        self.assertEqual(s["status"], "MIXED_UNITS_REVIEW")

    def test_mixed_modes_requires_review_first(self):
        s = classify_case("Korea-Institution-5-250PE-1Mreads-PE150-6Gb")
        self.assertEqual(s["status"], "MIXED_SEQUENCING_MODES_REVIEW")

    def test_no_depth_flagged(self):
        s = classify_case("Korea-Institution-5-PMP-250PE")
        self.assertEqual(s["status"], "UNIT_UNDETERMINED")

    def test_no_mode_flagged(self):
        s = classify_case("Korea-Institution-5-PMP-10Gb")
        self.assertEqual(s["status"], "MODE_UNDETERMINED")

    def test_normalizes_pe250_synonyms(self):
        for spelling in ("250PE", "PE250", "250-PE", "PE-250", "250 PE", "PE 250"):
            with self.subTest(spelling=spelling):
                self.assertEqual(normalize_mode(spelling), "PE250")

    def test_unit_mapping_other_modes_gb(self):
        for mode in ("PE150", "PE100", "SE100", "SE50", "PE75"):
            with self.subTest(mode=mode):
                self.assertEqual(operational_depth_unit(mode), "Gb")

    def test_unknown_mode_not_silent_gb(self):
        for mode in ("250", "longread", "", "PMP", "single cell"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                operational_depth_unit(mode)

    def test_near_dashes_read_length_not_sample_count(self):
        s = classify_case("Korea-Institution-5-PMP-250PE-1Mreads")
        self.assertEqual(s["modes"], ["PE250"])
        self.assertEqual(s["observed_units"], ["M reads"])

    def test_aggregation_has_only_counts(self):
        rows = [
            {"Quotation Name": "Korea-PrivateNameOne-5-PMP-250PE-1Mreads",
             "Opportunity Name": "Korea-PrivateNameOne-5-PMP-250PE-1Mreads"},
            {"Quotation Name": "Korea-PrivateNameTwo-5-PMP-PE250-4Gb",
             "Opportunity Name": "Korea-PrivateNameTwo-5-PMP-PE250-4Gb"},
            {"Quotation Name": "Korea-PrivateNameThree-5-PMP-PE150-6Gb",
             "Opportunity Name": "Korea-PrivateNameThree-5-PMP-PE150-6Gb"},
        ]
        metrics = summarize_case_pairs(rows)
        self.assertEqual(metrics["source_rows"], 3)
        self.assertEqual(metrics["quote_pe250_cases"], 2)
        self.assertEqual(metrics["quote_pe250_CURRENT_POLICY_ALIGNED"], 1)
        self.assertEqual(metrics["quote_pe250_HISTORICAL_UNIT_CONFLICT_REVIEW"], 1)
        self.assertEqual(metrics["pe250_quote_opportunity_same_units"], 2)
        self.assertNotIn("PrivateName", str(metrics))

    def test_empty_rows_do_not_produce_names(self):
        self.assertEqual(summarize_case_pairs([{}, {}, {"Quotation Name": ""}]), {})


class WebDraftPolicyTests(unittest.TestCase):
    def test_user_pmp_five_samples_one_mread(self):
        result = validate_request_draft(valid_draft())
        self.assertEqual(result["sample_count"], 5)
        self.assertEqual(result["sequencing_mode"], "PE250")
        self.assertEqual(result["depth_unit"], "M reads")
        self.assertEqual(result["depth_per_sample"], 1)
        self.assertEqual(result["total_nominal_depth"], 5)
        self.assertEqual(result["total_nominal_depth_unit"], "M reads")
        self.assertFalse(result["salesforce_save_allowed"])
        self.assertFalse(result["opportunity_created"])
        self.assertFalse(result["quotation_created"])
        self.assertFalse(result["price_verified"])

    def test_pe150_six_gb_pass(self):
        d = valid_draft()
        d.update(sequencing_mode="PE150", depth_per_sample=6, depth_unit="Gb")
        self.assertEqual(validate_request_draft(d)["total_nominal_depth"], 30)

    def test_pe150_cannot_use_mreads(self):
        d = valid_draft()
        d["sequencing_mode"] = "PE150"
        with self.assertRaises(ValueError):
            validate_request_draft(d)

    def test_pe250_cannot_use_gb_even_if_legacy_case(self):
        d = valid_draft()
        d["depth_unit"] = "Gb"
        with self.assertRaises(ValueError):
            validate_request_draft(d)

    def test_sample_count_must_be_integer(self):
        for value in (0, 2.5, -1, True, "5", 501):
            with self.subTest(value=value), self.assertRaises(ValueError):
                d = valid_draft()
                d["sample_count"] = value
                validate_request_draft(d)

    def test_no_price_or_salesforce_id_in_web_input(self):
        d = valid_draft()
        d["salesforce_record_id"] = "006000000000000AAA"
        with self.assertRaises(ValueError):
            validate_request_draft(d)

    def test_no_unspecified_units(self):
        d = valid_draft()
        d["depth_unit"] = ""
        with self.assertRaises(ValueError):
            validate_request_draft(d)

    def test_depth_positive(self):
        for depth in (0, -1, None, "1", False, float("nan")):
            with self.subTest(depth=depth), self.assertRaises(ValueError):
                d = valid_draft()
                d["depth_per_sample"] = depth
                validate_request_draft(d)

    def test_no_auto_pair_conversion(self):
        result = validate_request_draft(valid_draft())
        self.assertEqual(result["reads_basis"],
                         "UNSPECIFIED_WHETHER_READS_OR_READ_PAIRS")


if __name__ == "__main__":
    unittest.main()
