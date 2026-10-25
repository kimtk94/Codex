import unittest
from datetime import date
from next_best_action_leads import classify


class NextBestActionTests(unittest.TestCase):
    TODAY = date(2026, 10, 25)

    def test_sent_mail_excludes_lead(self):
        status, score, _ = classify({"Sent Mail Count": "1", "Due Date": "2025-01-01"}, self.TODAY)
        self.assertEqual((status, score), ("CONTACTED", 0))

    def test_decision_done_excludes_lead(self):
        status, score, _ = classify({"Decision Effective": "DONE", "Description Class": "DESCRIPTION_PRESENT"}, self.TODAY)
        self.assertEqual((status, score), ("CLOSED", 0))

    def test_converted_opportunity_separate(self):
        status, score, _ = classify({"Opportunity ID": "Opp-123", "Converted Date": "CONVERTED"}, self.TODAY)
        self.assertEqual((status, score), ("OPPORTUNITY", 0))

    def test_description_lead_ranks_above_forwarded(self):
        common = {"Due Date": "2026-10-24", "Description Intent": "SERVICE_INQUIRY"}
        _, high, _ = classify({**common, "Description Class": "DESCRIPTION_PRESENT"}, self.TODAY)
        _, low, _ = classify({**common, "Description Class": "DESCRIPTION_MISSING"}, self.TODAY)
        self.assertGreater(high, low)

    def test_overdue_age_is_capped(self):
        common = {"Description Class": "DESCRIPTION_PRESENT"}
        _, old, _ = classify({**common, "Due Date": "2025-01-01"}, self.TODAY)
        _, older, _ = classify({**common, "Due Date": "2024-01-01"}, self.TODAY)
        self.assertEqual(old, older)


if __name__ == "__main__":
    unittest.main()
