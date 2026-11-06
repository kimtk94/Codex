#!/usr/bin/env python3
"""Only user's QQ CSS Contract notices establish owner PO projects."""
import unittest
from unittest import mock
from datetime import datetime, timezone
import contract_po_tracker as po


def row(subject, source=po.CSS, key="k", when="2026-11-06T09:00:00+09:00"):
    return {"Mail Key": key, "Subject": subject, "From": source,
            "Direction": "INBOUND", "Received At": when, "In Reply To": ""}


class OwnerContractScopeTests(unittest.TestCase):
    def test_crm_contract_alone_never_eligible(self):
        crm = po.event(row("Contract Created AMEA2026042239",
                           source=po.CRM_SENDER), po.CRM_SENDER)
        self.assertIsNone(crm)
        self.assertEqual(po.build_tracker([], "now"), [])

    def test_qq_owner_contract_with_crm_downstream_is_eligible(self):
        own = po.event(row("Contract Ready AMEA2026042239"), po.CSS)
        other = po.event(row("Final Report & Statement Ready AMEA2026042239",
                             source=po.CRM_SENDER, key="down",
                             when="2026-11-06T11:00:00+09:00"), po.CRM_SENDER)
        self.assertTrue(own["contract"])
        self.assertFalse(other["contract"])
        output=po.build_tracker([own,other], "now")
        self.assertEqual(len(output),1)
        self.assertEqual(output[0]["Contract Source"],"CSS")
        self.assertEqual(output[0]["Submission Inference"],
                         "ASSUMED_BY_DOWNSTREAM_NOTICE")
        po.apply_followup(output,{})
        self.assertEqual(output[0]["PO Followup Queue"],"PO_SUBMITTED_INFERRED")

    def test_crm_other_sales_contract_plus_crm_downstream_creates_nothing(self):
        foreign = po.event(row("Contract Ready AMEA2026042239",
                               source=po.CRM_SENDER),po.CRM_SENDER)
        crm_report=po.event(row("Statement Issued AMEA2026042239",
                                source=po.CRM_SENDER, key="statement",
                                when="2026-11-06T11:00:00+09:00"),po.CRM_SENDER)
        self.assertIsNone(foreign)
        self.assertEqual(po.build_tracker([crm_report],"now"),[])

    def test_owner_contract_with_crm_po_notice_allowed(self):
        c=po.event(row("Contract Ready AMEA2026042239"),po.CSS)
        e=po.event(row("PO Received AMEA2026042239",source=po.CRM_SENDER,
                       when="2026-11-06T11:00:00+09:00",key="po"),po.CRM_SENDER)
        output=po.build_tracker([c,e],"now")
        self.assertEqual(output[0]["PO Status"],"PO_RECEIVED_NOTICE")
        self.assertEqual(output[0]["Contract Source"],"CSS")

    def test_malicious_prebuilt_crm_contract_cannot_create_owner(self):
        c=po.event(row("Contract Ready AMEA2026042239"),po.CSS)
        c["source"]="CRM"
        self.assertEqual(po.build_tracker([c],"now"),[])

    def test_owner_and_crm_mixed_same_project_owner_contract_only(self):
        css=po.event(row("Contract Ready AMEA2026042239",key="mine"),po.CSS)
        foreign={"project":css["project"],"at":css["at"],
                 "key":"other", "source":"CRM", "contract":True,
                 "po":None, "downstream":frozenset()}
        output=po.build_tracker([foreign,css],"now")
        self.assertEqual(output[0]["Contract Mail Key"],"mine")
        self.assertEqual(output[0]["Contract Source"],"CSS")

    def test_out_of_scope_tracker_rows_hidden_but_preserved(self):
        old={"record_id":"foreign_row","fields":{
            "Project ID":"AMEA2026042250", "Contract Source":"CRM",
            "Contract Mail Key":"old_mail", "PO Status":"PO_REQUIRED",
            "PO Followup Queue":"PO_REQUIRED",
            "PO Document Verification":"FILE_VERIFIED",
            "PO Document Reference":"internal:document",
            "PO Verified By":"owner", "PO Verified At":"2026-11-06T10:00:00+09:00",
        }}
        stored=dict(old["fields"])
        writes=[]
        def api(method,path,token,data,action):
            self.assertEqual(method,"POST")
            self.assertEqual(action,"contract_po_batch_update")
            self.assertEqual(len(data["records"]),1)
            update=data["records"][0]
            self.assertEqual(update["record_id"],"foreign_row")
            fields=update["fields"]
            self.assertEqual(fields["PO Followup Queue"],"EXCLUDED_NO_OWNER_CONTRACT")
            self.assertEqual(fields["Next Action"],"NO_PO_REQUEST_OUT_OF_SCOPE")
            self.assertNotIn("PO Document Reference",fields)
            self.assertNotIn("Contract Mail Key",fields)
            writes.append(fields)
            return {"records":[{"record_id":"foreign_row"}]}
        def list_records(path,token,action):
            if action=="contract_po_existing":
                return [old]
            if action=="contract_po_readback":
                return [{"record_id":"foreign_row",
                         "fields":{**stored,**writes[0]}}]
            raise AssertionError(action)
        with mock.patch.object(po,"list_all",side_effect=list_records), \
             mock.patch.object(po,"api",side_effect=api):
            self.assertEqual(po.sync("token","path",[]),(0,1,0))
        self.assertEqual(stored["Contract Mail Key"],"old_mail")
        self.assertEqual(stored["PO Document Reference"],"internal:document")

    def test_no_extra_writes_when_prior_owner_scope_already_excluded(self):
        prior={"record_id":"existing","fields":{
            "Project ID":"AMEA2026042250", "Contract Source":"CRM",
            "PO Followup Queue":"EXCLUDED_NO_OWNER_CONTRACT",
            "Next Action":"NO_PO_REQUEST_OUT_OF_SCOPE",
        }}
        with mock.patch.object(po,"list_all",side_effect=[[prior],[prior]]), \
             mock.patch.object(po,"api") as api:
            self.assertEqual(po.sync("token","path",[]),(0,0,0))
        api.assert_not_called()

    def test_readback_guard_fails_if_old_customer_still_in_due_list(self):
        old={"record_id":"foreign","fields":{
            "Project ID":"AMEA2026042250","Contract Source":"CRM",
            "PO Followup Queue":"PO_REQUIRED", "Next Action":"REQUEST_PO"}}
        def api(method,path,token,data,action):
            return {"records":[{"record_id":"foreign"}]}
        with mock.patch.object(po,"list_all",side_effect=[[old],[old]]), \
             mock.patch.object(po,"api",side_effect=api):
            with self.assertRaisesRegex(po.SafeError,"OUT_OF_SCOPE_NOT_EXCLUDED"):
                po.sync("token","path",[])


if __name__=="__main__":
    unittest.main()
