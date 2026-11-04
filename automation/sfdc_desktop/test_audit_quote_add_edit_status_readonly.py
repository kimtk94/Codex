import unittest
from audit_quote_add_edit_status_readonly import choose_status_samples

def row(i, state="Draft", saved=False):
    return {"quote_id": f"a0P{i:012d}AAA", "quote_status":state, "save_clicked":saved}

class SamplingTests(unittest.TestCase):
    def test_max_two_per_status(self):
        records=[row(i,"Draft") for i in range(3)]
        self.assertEqual(len(choose_status_samples(records)),2)

    def test_rejected_excluded(self):
        self.assertEqual(choose_status_samples([row(1,"Rejected")]),[])

    def test_saved_reference_excluded(self):
        self.assertEqual(choose_status_samples([row(1,saved=True)]),[])

    def test_duplicate_excluded(self):
        self.assertEqual(len(choose_status_samples([row(1),row(1)])),1)

    def test_three_repeat(self):
        r=[choose_status_samples([row(1),row(2)]) for _ in range(3)]
        self.assertEqual(r[0],r[1])
        self.assertEqual(r[1],r[2])

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            choose_status_samples([],per_status=4)

if __name__=="__main__":
    unittest.main()
