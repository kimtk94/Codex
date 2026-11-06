#!/usr/bin/env python3
"""Offline SIF lifecycle tests: authoritative notices, not document verification."""
import unittest
from unittest import mock
import sif_evidence_tracker as s
import contract_po_tracker as po


def row(subject, sender=po.CSS, key="id-1", when="2026-11-06T10:00:00+09:00", **extras):
    fields = {
        "Mail Key": key, "Subject": subject, "From": sender,
        "Direction": "INBOUND", "Received At": when, "In Reply To": "",
    }
    fields.update(extras)
    return fields


def e(subject, **opts):
    r = row(subject, **opts)
    return s.sif_event(r, r["From"])


def contract(subject="Contract Ready AMEA2026042239"):
    return po.event(row(subject), po.CSS)


class SIFTrackerTests(unittest.TestCase):
    def test_contract_without_sif_is_review_not_proof_of_missing(self):
        records = s.build_rows([contract()], [], "now")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["SIF Status"], "SIF_NOT_OBSERVED")
        self.assertEqual(records[0]["Next Action"], "CHECK_SIF_WITH_OWNER")
        self.assertEqual(records[0]["SIF Followup Queue"], "REVIEW_REQUIRED")

    def test_sif_submitted_before_contract_is_visible(self):
        submitted = e("SIF submitted AMEA2026042239")
        records = s.build_rows([], [submitted], "now")
        self.assertEqual(records[0]["SIF Status"], "SIF_SUBMITTED_NOTICE")
        self.assertEqual(records[0]["Contract Notice"], "NO")
        self.assertEqual(records[0]["Next Action"], "VERIFY_SIF_RECEIPT")

    def test_sif_approved_is_only_approval_notice(self):
        r = s.build_rows([contract()], [e("SIF Approved AMEA2026042239")], "now")[0]
        self.assertEqual(r["SIF Status"], "SIF_APPROVED_NOTICE")
        self.assertEqual(r["SIF Followup Queue"], "APPROVAL_NOTICE_OBSERVED")
        self.assertEqual(r["Next Action"], "VERIFY_APPROVAL_AND_SIF_FILE")

    def test_request_then_receipt_then_approval(self):
        msgs = [e("Please Submit SIF AMEA2026042239", key="one",
                  when="2026-11-04T10:00:00+09:00"),
                e("SIF Received AMEA2026042239", key="two",
                  when="2026-11-05T10:00:00+09:00"),
                e("SIF Approved AMEA2026042239", key="three",
                  when="2026-11-06T10:00:00+09:00")]
        r = s.build_rows([contract()], msgs, "now")[0]
        self.assertEqual(r["SIF Status"], "SIF_APPROVED_NOTICE")
        self.assertEqual(r["SIF Mail Key"], "three")

    def test_rejected_after_approval_is_ambiguous(self):
        msgs = [e("SIF Approved AMEA2026042239", key="early",
                  when="2026-11-05T10:00:00+09:00"),
                e("SIF rejected AMEA2026042239", key="late",
                  when="2026-11-06T10:00:00+09:00")]
        r = s.build_rows([], msgs, "now")[0]
        self.assertEqual(r["SIF Status"], "SIF_REVIEW")
        self.assertEqual(r["Next Action"], "REVIEW_POST_APPROVAL_SIF_NOTICE")

    def test_conflicting_simultaneous_notices_require_review(self):
        a = e("SIF Approved AMEA2026042239", key="a")
        b = e("SIF rejected AMEA2026042239", key="b")
        r = s.build_rows([], [a, b], "now")[0]
        self.assertEqual(r["SIF Status"], "SIF_REVIEW")
        self.assertEqual(r["SIF Mail Key"], "")

    def test_mentions_cannot_override_approved_notice(self):
        approved = e("SIF Approved AMEA2026042239", key="approved",
                     when="2026-11-05T10:00:00+09:00")
        mention = e("SIF status AMEA2026042239", key="mention",
                    when="2026-11-06T10:00:00+09:00")
        r = s.build_rows([], [approved, mention], "now")[0]
        self.assertEqual(r["SIF Status"], "SIF_APPROVED_NOTICE")

    def test_exact_source_and_reply_required(self):
        self.assertIsNone(s.sif_event(row("SIF Approved AMEA2026042239",
                                          sender="crm@novogene.com.bad"), po.CRM_SENDER))
        self.assertIsNone(s.sif_event(row("Re: SIF Approved AMEA2026042239"), po.CSS))
        self.assertIsNone(s.sif_event(row("SIF Approved AMEA2026042239",
                                          **{"In Reply To": "<previous>"}), po.CSS))
        self.assertIsNone(s.sif_event(row("SIF Approved AMEA2026042239",
                                          when="2025-11-06T10:00:00+09:00"), po.CSS))
        self.assertIsNone(s.sif_event(row("SIF Approved AMEA2026042239",
                                          Direction="OUTBOUND"), po.CSS))

    def test_ambiguous_id_never_guessed(self):
        m = e("SIF approved AMEA2026042239 AMEA2026042240")
        self.assertIsNone(m["project"])
        self.assertEqual(s.build_rows([], [m], "now"), [])

    def test_body_only_sif_notice_not_used_for_approval(self):
        self.assertIsNone(s.sif_event(
            row("Progress AMEA2026042239", **{"Body Excerpt": "SIF Approved"}), po.CSS))
        unlinked = s.sif_event(
            row("SIF Approved", **{"Body Excerpt": "AMEA2026042239"}), po.CSS
        )
        self.assertIsNone(unlinked["project"])
        self.assertEqual(s.build_rows([], [unlinked], "now"), [])

    def test_different_projects_stay_separate(self):
        rows = s.build_rows([], [e("SIF Approved AMEA2026042239"),
                                 e("SIF Received AMEA2026042240", key="two")], "now")
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["SIF Status"], rows[1]["SIF Status"])

    def test_sync_unchanged_is_read_only(self):
        d = s.build_rows([contract()], [], "now")
        existing = [{"record_id": "rec", "fields": dict(d[0])}]
        with mock.patch.object(s, "list_all", side_effect=[existing, existing]), \
             mock.patch.object(s, "api") as api:
            result = s.sync("token", "path", d)
        self.assertEqual(result, (0, 0))
        api.assert_not_called()

    def test_sync_readback_missing_is_error(self):
        d = s.build_rows([contract()], [], "now")
        with mock.patch.object(s, "list_all", side_effect=[[], []]), \
             mock.patch.object(s, "api", return_value={
                 "records": [{"record_id": "rec"}]}):
            with self.assertRaisesRegex(s.SafeError, "READBACK_MISMATCH"):
                s.sync("token", "path", d)

    def test_source_namespace_guard(self):
        data = {"name": "CRM Filtered Mail Intake", "table_id": "c"}
        with mock.patch.object(s, "list_all", side_effect=[
                [data, {"name": "QQ Mail Intake", "table_id": "q"}],
                [{"fields": row("SIF Approved AMEA2026042239", po.CSS)}],
                [{"fields": {**row("SIF Approved AMEA2026042240", po.CRM_SENDER),
                            "Source Account": "wrong", "Source Filter": "EXACT_FROM_CRM"}}],
        ]):
            tables, contracts, events, counts = s.load_sources("token", "root")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["project"], "AMEA2026042239")


if __name__ == "__main__":
    unittest.main()
