"""Synthetic display-HOLD diagnostics; no customer records, no CRM requests."""
import unittest
from diagnose_contact_display_holds_private import name_presentation


class ContactDisplayDiagnoseTests(unittest.TestCase):
    def test_bilingual_heading(self):
        self.assertEqual(name_presentation("김민수 KimMinSu", [], ["김민수 KimMinSu"]),
                         "FULL_NAME_HEADING")

    def test_exact_text_without_heading(self):
        self.assertEqual(name_presentation("김민수 KimMinSu", ["김민수 KimMinSu"], []),
                         "FULL_NAME_VISIBLE")

    def test_unicode_space_normalization(self):
        self.assertEqual(name_presentation("김민수 KimMinSu", ["  김민수   KimMinSu  "], []),
                         "FULL_NAME_VISIBLE")

    def test_only_korean_short_label(self):
        self.assertEqual(name_presentation("김민수 KimMinSu", ["김민수"], []),
                         "ONLY_KOREAN_TOKEN_VISIBLE")

    def test_korean_token_in_longer_text_not_pass(self):
        self.assertEqual(name_presentation("김민수 KimMinSu", ["담당 김민수 선임"], []),
                         "KOREAN_TOKEN_IN_LONGER_TEXT")

    def test_english_romanization_not_sufficient(self):
        self.assertEqual(name_presentation("김민수 KimMinSu", ["KimMinSu"], []),
                         "NO_EXPECTED_DISPLAY_VISIBLE")

    def test_ambiguous_display_not_inferred(self):
        self.assertEqual(name_presentation("KimMinSu 김민수", ["김민수"], []),
                         "NO_EXPECTED_DISPLAY_VISIBLE")

    def test_three_pass_deterministic(self):
        outcomes=[name_presentation("김민수 KimMinSu", ["김민수"], []) for _ in range(3)]
        self.assertEqual(len(set(outcomes)),1)


if __name__=="__main__":
    unittest.main()
