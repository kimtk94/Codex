#!/usr/bin/env python3
"""Contract creation gates the PO-required queue; safe independent regression."""
import unittest
from datetime import datetime, timezone, timedelta
import contract_po_tracker as p


def message(subject, sender="css@novogene-amea.com", uid="one", **override):
    f = {"Subject": subject, "From": sender, "Direction": "INBOUND",
         "Mail Key": "key-" + uid, "In Reply To": "",
         "Received At": "2026-11-06T10:00:00+09:00"}
    f.update(override)
    return f


class ContractPOTrackerTests(unittest.TestCase):
    def test_contract_ready_creates_po_needed(self):
        e = p.event(message("Contract Ready AMEA2026042239"), p.CSS)
        self.assertTrue(e["contract"])
        rows = p.build_tracker([e], "now")
        self.assertEqual(rows[0]["PO Status"], "PO_REQUIRED")
        self.assertEqual(rows[0]["Next Action"], "REQUEST_PO")

    def test_crm_contract_cannot_create_an_owner_project(self):
        # Jiin is a different salesperson's mixed mail intake.
        e = p.event(message("Contract Created AMEA2026042239",
                            sender="crm@novogene.com"), p.CRM_SENDER)
        self.assertIsNone(e)

    def test_po_notice_without_contract_does_not_create_queue(self):
        e = p.event(message("PO Received AMEA2026042239",
                            sender="crm@novogene.com"), p.CRM_SENDER)
        self.assertFalse(e["contract"])
        self.assertEqual(p.build_tracker([e], "now"), [])

    def test_receipt_after_contract_moves_out_of_due_queue(self):
        c = p.event(message("Contract Ready AMEA2026042239"), p.CSS)
        r = p.event(message("Purchase Order Received AMEA2026042239", uid="two",
                            sender=p.CRM_SENDER, **{
                                "Received At": "2026-11-06T11:00:00+09:00"
                            }), p.CRM_SENDER)
        rows = p.build_tracker([c, r], "now")
        self.assertEqual(rows[0]["PO Status"], "PO_RECEIVED_NOTICE")
        self.assertEqual(rows[0]["Next Action"], "VERIFY_PO_FILE")

    def test_po_pending_stays_in_due_queue(self):
        c = p.event(message("Contract Ready AMEA2026042239"), p.CSS)
        r = p.event(message("PO not received AMEA2026042239",
                            sender=p.CRM_SENDER, uid="two"), p.CRM_SENDER)
        self.assertEqual(p.build_tracker([c, r], "now")[0]["PO Status"], "PO_REQUIRED")

    def test_later_missing_notice_reopens_due_queue(self):
        c = p.event(message("Contract Ready AMEA2026042239"), p.CSS)
        rec = p.event(message("PO Received AMEA2026042239", uid="two",
                              sender=p.CRM_SENDER), p.CRM_SENDER)
        missing = p.event(message("PO not received AMEA2026042239", uid="three",
                                  sender=p.CRM_SENDER,
                                  **{"Received At": "2026-11-06T12:00:00+09:00"}), p.CRM_SENDER)
        self.assertEqual(p.build_tracker([c, rec, missing], "now")[0]["PO Status"], "PO_REQUIRED")

    def test_unverified_or_negated_contract_does_not_start(self):
        self.assertIsNone(p.event(message("Contract not ready AMEA2026042239"), p.CSS))
        self.assertIsNone(p.event(message("Re: Contract Ready AMEA2026042239"), p.CSS))
        self.assertIsNone(p.event(message("Contract Ready AMEA2026042239",
                                          **{"In Reply To": "<abc@domain>"}), p.CSS))
        self.assertIsNone(p.event(message("Contract Ready AMEA2026042239", sender="evil@example.com"), p.CSS))

    def test_identifier_never_joined_from_body(self):
        self.assertIsNone(p.event(message("Contract Ready", **{"Body Excerpt": "AMEA2026042239"}), p.CSS))
        self.assertIsNone(p.event(message("Contract Ready AMEA2026042239 AMEA2026042240"), p.CSS))
        self.assertEqual(p.unique_project("Contract Ready AMEA2026042239 H209SC26065705"),
                         "AMEA2026042239")

    def test_before_2026_and_noninbound_refused(self):
        self.assertIsNone(p.event(message("Contract Ready AMEA2026042239",
                                          **{"Received At": "2025-12-31T11:00:00+09:00"}), p.CSS))
        self.assertIsNone(p.event(message("Contract Ready AMEA2026042239",
                                          Direction="OUTBOUND"), p.CSS))

    def test_multiple_contract_notices_deduped_by_project(self):
        first = p.event(message("Contract Created AMEA2026042239"), p.CSS)
        second = p.event(message("Contract Ready AMEA2026042239", uid="second"), p.CSS)
        rows = p.build_tracker([first, second], "now")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Contract Mail Key"], "key-one")


if __name__ == "__main__":
    unittest.main()
