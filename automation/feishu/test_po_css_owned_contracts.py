#!/usr/bin/env python3
"""Sales ownership: CSS creates Contract cohort, Jiin CRM supplies evidence only."""
import unittest
from unittest import mock
import contract_po_tracker as po


def mail(subject, sender=po.CSS, uid="m", at="2026-11-06T10:00:00+09:00", **more):
    f = {
        "Subject": subject, "From": sender, "Direction": "INBOUND",
        "Mail Key": uid, "In Reply To": "", "Received At": at,
    }
    f.update(more)
    return f


def event(subject, sender=po.CSS, uid="m", at="2026-11-06T10:00:00+09:00"):
    return po.event(mail(subject, sender, uid, at), sender)


class CSSOwnedContractTests(unittest.TestCase):
    def test_css_creates_owned_contract(self):
        e = event("Contract Ready AMEA2026042239", uid="css-contract")
        self.assertTrue(e["contract"])
        row = po.build_tracker([e], "now")[0]
        self.assertEqual(row["Contract Source"], "CSS")
        self.assertEqual(row["Contract Scope"], "MY_CSS_CONTRACT")
        self.assertEqual(row["Contract Mail Key"], "css-contract")

    def test_jiin_crm_contract_alone_creates_no_row(self):
        e = event("Contract Ready AMEA2026042239", po.CRM_SENDER)
        self.assertIsNone(e)
        self.assertEqual(po.build_tracker([], "now"), [])

    def test_many_jiin_crm_contracts_do_not_expand_owned_cohort(self):
        owned = event("Contract Ready AMEA2026042239", uid="css-contract")
        other = [
            event("Contract Ready AMEA2026042240", po.CRM_SENDER, uid="crm1"),
            event("Contract Ready AMEA2026042241", po.CRM_SENDER, uid="crm2"),
        ]
        self.assertEqual(len(po.build_tracker([owned] + [x for x in other if x], "now")), 1)

    def test_jiin_crm_po_received_after_css_contract_is_supplementary(self):
        owned = event("Contract Ready AMEA2026042239", uid="owned")
        rec = event("PO Received AMEA2026042239", po.CRM_SENDER, "crm-po",
                    "2026-11-06T11:00:00+09:00")
        row = po.build_tracker([owned, rec], "now")[0]
        self.assertEqual(row["Contract Source"], "CSS")
        self.assertEqual(row["PO Status"], "PO_RECEIVED_NOTICE")
        self.assertEqual(row["PO Notice Source"], "CRM")

    def test_jiin_crm_report_after_css_contract_is_supplementary(self):
        owned = event("Contract Ready AMEA2026042239", uid="owned")
        report = event("Final Report & Statement Ready AMEA2026042239",
                       po.CRM_SENDER, "crm-report", "2026-11-06T11:00:00+09:00")
        row = po.build_tracker([owned, report], "now")[0]
        po.apply_followup([row], {})
        self.assertEqual(row["Contract Source"], "CSS")
        self.assertEqual(row["Downstream Source"], "CRM")
        self.assertEqual(row["PO Followup Queue"], "PO_SUBMITTED_INFERRED")

    def test_jiin_crm_contract_and_report_without_css_not_ours(self):
        other_contract = event("Contract Ready AMEA2026042240", po.CRM_SENDER, "crm-only")
        other_report = event("Statement Issued AMEA2026042240", po.CRM_SENDER,
                             "crm-statement", "2026-11-06T12:00:00+09:00")
        self.assertEqual(po.build_tracker([x for x in
                                            (other_contract, other_report) if x], "now"), [])

    def test_po_before_css_contract_cannot_prove_postcontract_delivery(self):
        before = event("PO Received AMEA2026042239", po.CRM_SENDER, "pre",
                       "2026-11-06T09:00:00+09:00")
        owned = event("Contract Created AMEA2026042239", uid="css-contract")
        row = po.build_tracker([before, owned], "now")[0]
        self.assertEqual(row["PO Status"], "PO_REQUIRED")

    def test_historical_other_sales_row_archived_without_deleting_or_erasing_manual_evidence(self):
        c = event("Contract Ready AMEA2026042239", uid="mine")
        mine = po.build_tracker([c], "now")[0]
        po.apply_followup([mine], {})
        old_other = {
            "Project ID": "AMEA2026042240", "Contract Source": "CRM",
            "Contract Scope": "", "PO Status": "PO_REQUIRED",
            "PO Followup Queue": "PO_REQUIRED", "Next Action": "REQUEST_PO",
            "PO Document Verification": "FILE_VERIFIED",
            "PO Document Reference": "historical-file-ref",
        }
        existing = [
            {"record_id": "owned-rec", "fields": mine.copy()},
            {"record_id": "other-rec", "fields": old_other.copy()},
        ]
        calls = []
        def api(method, path, token, data=None, action=None):
            self.assertEqual(method, "POST")
            self.assertTrue(path.endswith("batch_update"))
            writes = data["records"]
            calls.extend(writes)
            return {"records": [{"record_id": x["record_id"]} for x in writes]}
        def fetch(path, token, action):
            if action == "contract_po_existing":
                return existing
            self.assertEqual(action, "contract_po_readback")
            out = {x["record_id"]: dict(x["fields"]) for x in existing}
            for change in calls:
                out[change["record_id"]].update(change["fields"])
            return [{"record_id": k, "fields": v} for k, v in out.items()]
        with mock.patch.object(po, "list_all", side_effect=fetch), \
             mock.patch.object(po, "api", side_effect=api):
            self.assertEqual(po.sync("token", "table", [mine]), (0, 1, 1))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["record_id"], "other-rec")
        self.assertEqual(calls[0]["fields"]["PO Followup Queue"],
                         "OUT_OF_SCOPE_OTHER_SALES")
        self.assertEqual(calls[0]["fields"]["Contract Scope"],
                         "EXCLUDED_NOT_MY_CSS_CONTRACT")
        self.assertNotIn("PO Document Reference", calls[0]["fields"])
        self.assertNotIn("PO Document Verification", calls[0]["fields"])

    def test_archival_is_idempotent(self):
        c = event("Contract Ready AMEA2026042239")
        mine = po.build_tracker([c], "now")[0]
        po.apply_followup([mine], {})
        old_other = {
            "Project ID": "AMEA2026042240", "Contract Scope": "EXCLUDED_NOT_MY_CSS_CONTRACT",
            "PO Followup Queue": "OUT_OF_SCOPE_OTHER_SALES",
            "Next Action": "NO_ACTION_OTHER_SALES_CONTRACT",
        }
        existing = [
            {"record_id": "mine", "fields": mine.copy()},
            {"record_id": "other", "fields": old_other},
        ]
        with mock.patch.object(po,"list_all",side_effect=[existing,existing]), \
             mock.patch.object(po,"api") as writes:
            self.assertEqual(po.sync("t", "p", [mine]), (0,0,1))
            writes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
