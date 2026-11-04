"""Synthetic-only regression tests for the private Korean Contact batch adapter."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import live_contact_alias_batch_private as adapter
from build_private_contact_aliases import verified_private_aliases

C="003000000000001AAA"
O="006000000000001AAA"
A="001000000000001AAA"


def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8")


class PrivateContactBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.mock=patch.object(adapter,"ROOT",self.folder)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        save(self.folder/"oppo_linked_contact_candidate_manifest_PRIVATE.json",[
            {"opportunity_id":O,"contact_display":"김민수 KimMinSu"}])
        save(self.folder/"oppo_main_contact_identity_batch180_PRIVATE.json",[
            {"opportunity_id":O,"result":"PASS_ID_AND_CANDIDATE","actual_contact_ids":[C]}])
        save(self.folder/"full_contact_with_names_PRIVATE.json",{"rows":[
            {"id":C,"name":"김민수 KimMinSu","cells":["demo@example.org"]}]})

    def test_explicit_korean_name_candidate(self):
        rows=adapter.candidates()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["opportunity_id"],O)
        self.assertEqual(rows[0]["contact_id"],C)

    def test_non_verified_opportunity_not_candidate(self):
        save(self.folder/"oppo_main_contact_identity_batch180_PRIVATE.json",[
            {"opportunity_id":O,"result":"HOLD_ERROR","actual_contact_ids":[C]}])
        self.assertEqual(adapter.candidates(),[])

    def test_missing_email_held(self):
        save(self.folder/"full_contact_with_names_PRIVATE.json",{"rows":[
            {"id":C,"name":"김민수 KimMinSu","cells":[]}]})
        self.assertEqual(adapter.candidates(),[])

    def test_wrong_name_registry_held(self):
        save(self.folder/"full_contact_with_names_PRIVATE.json",{"rows":[
            {"id":C,"name":"김영희 KimYoungHee","cells":["demo@example.org"]}]})
        self.assertEqual(adapter.candidates(),[])

    def test_english_only_name_not_inferred(self):
        save(self.folder/"oppo_linked_contact_candidate_manifest_PRIVATE.json",[
            {"opportunity_id":O,"contact_display":"KimMinSu"}])
        self.assertEqual(adapter.candidates(),[])

    def test_email_collision_held(self):
        save(self.folder/"full_contact_with_names_PRIVATE.json",{"rows":[
            {"id":C,"name":"김민수 KimMinSu","cells":["first@example.org","second@example.org"]}]})
        self.assertEqual(adapter.candidates(),[])

    def test_passing_evidence_matches_web_schema(self):
        row={**adapter.candidates()[0],
            "opportunity_ids":[O],"account_id":A,"institution":"서울대학교",
            "contact_detail_id_verified":True,"contact_account_link_verified":True,
            "opportunity_contact_link_verified":True,"contact_email_verified":True,
            "contact_display_name_verified":True}
        data=verified_private_aliases([row])
        self.assertEqual(len(data["records"]),1)
        self.assertEqual(data["records"][0]["opportunity_ids"],[O])
        self.assertEqual(data["records"][0]["name"],"김민수")
        self.assertFalse(data["save_allowed"])

    def test_missing_link_id_list_never_exported(self):
        row={**adapter.candidates()[0],
            "account_id":A,"institution":"서울대학교",
            "contact_detail_id_verified":True,"contact_account_link_verified":True,
            "opportunity_contact_link_verified":True,"contact_email_verified":True,
            "contact_display_name_verified":True}
        self.assertEqual(verified_private_aliases([row])["records"],[])


if __name__=="__main__":
    unittest.main()
