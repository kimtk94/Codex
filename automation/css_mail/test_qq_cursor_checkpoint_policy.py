"""No network, no Sheets or cursor writes: checkpoint policy regression tests."""
import unittest
from automation.css_mail.qq_cursor_checkpoint_policy import (
    conservative_cursor, assess_writer_cursor_order
)


class CheckpointPolicyTests(unittest.TestCase):
    def test_known_and_verified_prefix_can_advance(self):
        result = conservative_cursor(100, [101,103,108], {
            101:"KNOWN_UID_WITH_VALID_EVIDENCE",
            103:"ORIGINAL_ISSUED_PROOF_PERSISTED",
            108:"ORIGINAL_NONOFFICIAL_HEADER_VERIFIED",
        })
        self.assertEqual(result["checkpoint_safe"],108)
        self.assertEqual(result["unresolved_count"],0)
        self.assertEqual(result["cursor_writes"],0)

    def test_first_fetch_failure_blocks_all_cursor_progress(self):
        r = conservative_cursor(100,[101,103,108],{
            101:"FETCH_FAILED",
            103:"ORIGINAL_ISSUED_PROOF_PERSISTED",
            108:"KNOWN_UID_WITH_VALID_EVIDENCE",
        })
        self.assertEqual(r["checkpoint_safe"],100)
        self.assertEqual(r["unresolved_count"],1)
        self.assertTrue(r["blocked"])

    def test_unresolved_middle_does_not_skip_ahead(self):
        r = conservative_cursor(100,[101,103,108],{
            101:"KNOWN_UID_WITH_VALID_EVIDENCE",
            103:"MIME_PARSER_UNRESOLVED",
            108:"ORIGINAL_ISSUED_PROOF_PERSISTED",
        })
        self.assertEqual(r["checkpoint_safe"],101)

    def test_amount_conflict_blocks_replay(self):
        r = conservative_cursor(100,[101,103],{
            101:"AMOUNT_CONFLICT",
            103:"ORIGINAL_ISSUED_PROOF_PERSISTED",
        })
        self.assertEqual(r["checkpoint_safe"],100)

    def test_incomplete_outcome_map_is_blocked(self):
        with self.assertRaisesRegex(ValueError,"OUTCOME_COVERAGE_INCOMPLETE"):
            conservative_cursor(100,[101,102],{101:"FETCH_FAILED"})

    def test_unordered_or_duplicate_uid_is_blocked(self):
        for candidates in ([103,101],[101,101],[100,101]):
            with self.assertRaisesRegex(ValueError,"CANDIDATE_ORDER_OR_SCOPE_INVALID"):
                conservative_cursor(100,candidates,{})

    def test_unknown_status_not_treated_as_safe(self):
        with self.assertRaisesRegex(ValueError,"OUTCOME_UNKNOWN"):
            conservative_cursor(100,[101],{101:"UNREVIEWED_SKIP"})

    def test_no_candidates_cannot_invent_new_checkpoint(self):
        r = conservative_cursor(100,[],{})
        self.assertEqual(r["checkpoint_safe"],100)
        self.assertFalse(r["checkpoint_would_advance"])

    def test_detects_early_advancement_pattern(self):
        source = (
            "last_by_folder = {}\n"
            "for uid in eligible:\n"
            "    last_by_folder[folder] = uid\n"
            "    result = im.uid('FETCH', uid, '(BODYSTRUCTURE)')\n"
        )
        r=assess_writer_cursor_order(source)
        self.assertTrue(r["early_cursor_advance_detected"])
        self.assertFalse(r["writer_mutated"])

    def test_missing_ast_evidence_never_asserts_safety(self):
        with self.assertRaisesRegex(ValueError,"WRITER_CURSOR_ORDER_UNVERIFIED"):
            assess_writer_cursor_order("last_by_folder = {}\n")


if __name__=="__main__":
    unittest.main()
