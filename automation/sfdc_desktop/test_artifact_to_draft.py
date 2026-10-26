import unittest
from artifact_to_draft import prepare

class ArtifactToDraftTests(unittest.TestCase):
    def test_safe_draft_from_verified_artifact(self):
        source={"salesforce_save_performed":False,"matches":[
            {"opportunity_id":"Opp-1","account":"Yonsei","contact":"Kim",
             "account_id":"001","contact_cms_id":"CP"}]}
        d=prepare(source)
        self.assertEqual(d["Account Name"],"Yonsei")
        self.assertEqual(d["Amount"],"")
        self.assertFalse(d["save_allowed"])
        self.assertFalse(d["lookup_verified"])
    def test_missing_marker_rejected(self):
        with self.assertRaises(ValueError):
            prepare({"matches":[{"opportunity_id":"x","account":"A","contact":"B"}]})
if __name__=="__main__":
    unittest.main()
