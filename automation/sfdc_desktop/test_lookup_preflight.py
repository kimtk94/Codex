import unittest
from lookup_preflight import prepare_lookup
class LookupDraftTests(unittest.TestCase):
    def test_requires_safe_flags(self):
        x={"Account Name":"Yonsei","Main Contact":"Kim","save_allowed":False,"lookup_verified":False}
        self.assertEqual(prepare_lookup(x)["Account Name"],"Yonsei")
        with self.assertRaises(ValueError):
            prepare_lookup({**x,"save_allowed":True})
    def test_missing_contact_blocked(self):
        with self.assertRaises(ValueError):
            prepare_lookup({"Account Name":"A","save_allowed":False,"lookup_verified":False})
if __name__=="__main__":
    unittest.main()
