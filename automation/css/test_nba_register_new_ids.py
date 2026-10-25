import unittest
from nba_register_new_ids import register


class RegistrationTests(unittest.TestCase):
    def test_append_only_preserves_checked_rows(self):
        existing=[{"Source":"CSS","Record ID":"ACT-1","완료 체크":"TRUE"},
                  {"Source":"QQ_MAIL","Record ID":"inbox:1","완료 체크":"FALSE"}]
        pool=[{"Source":"LEAD","Record ID":"Lead-3"},
              {"Source":"CSS","Record ID":"ACT-1"},
              {"Source":"LEAD","Record ID":"Lead-3"}]
        out,added=register(existing,pool)
        self.assertEqual(added,1)
        self.assertEqual([r["Record ID"] for r in out],["ACT-1","inbox:1","Lead-3"])
        self.assertEqual(out[0]["완료 체크"],"TRUE")
        self.assertEqual(out[-1]["완료 체크"],"FALSE")

    def test_case_insensitive_ids(self):
        out,added=register([{"Source":"css","Record ID":"a","완료 체크":"TRUE"}],
                           [{"Source":"CSS","Record ID":"A"}])
        self.assertEqual((len(out),added),(1,0))

    def test_reject_duplicate_existing_keys(self):
        with self.assertRaises(ValueError):
            register([{"Source":"CSS","Record ID":"A"},
                      {"Source":"css","Record ID":"a"}],[])


if __name__=="__main__": unittest.main()
