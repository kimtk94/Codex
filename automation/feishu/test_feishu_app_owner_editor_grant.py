#!/usr/bin/env python3
import unittest
from feishu_app_owner_editor_grant import grant_plan, classify_existing, GrantError, BASE_TOKEN, ALLOW_EMAIL

class GrantTests(unittest.TestCase):
    def test_exact_one_editor(self):
        self.assertEqual(grant_plan(BASE_TOKEN,ALLOW_EMAIL),
                         {"member_type":"email","member_id":ALLOW_EMAIL,"perm":"edit"})
    def test_wrong_user_blocked(self):
        with self.assertRaises(GrantError):
            grant_plan(BASE_TOKEN,"anyone@novogene.com")
    def test_wrong_base_blocked(self):
        with self.assertRaises(GrantError):
            grant_plan("different_app",ALLOW_EMAIL)
    def test_already_editor(self):
        v=classify_existing([{"member_type":"email","member_id":ALLOW_EMAIL,"perm":"edit"}],ALLOW_EMAIL)
        self.assertEqual(v["perm"],"edit")
    def test_duplicate_blocked(self):
        with self.assertRaises(GrantError):
            classify_existing([{"member_type":"email","member_id":ALLOW_EMAIL},
                               {"member_type":"email","member_id":ALLOW_EMAIL}],ALLOW_EMAIL)
if __name__=="__main__":
    unittest.main()
