import unittest
from invoice_ownership import classify_mail, classify_invoice

class OwnershipTests(unittest.TestCase):
    def test_other_staff_forward(self):
        self.assertEqual(classify_invoice("hyunseok.koo@novogene.com", "ns@n-s.co.kr", "sales.korea@novogene-amea.com")[0],
                         "EXCLUDE_FROM_PERSONAL_REVENUE_UNLESS_OWNER_VERIFIED")
    def test_internal_etax_thread(self):
        self.assertEqual(classify_mail("jiin.yoo@novogene.com","ally.shin@novogene.com","sales.korea@novogene-amea.com"),"SHARED_OR_OTHER_PERSON_MAIL")
    def test_css_user_cc(self):
        self.assertEqual(classify_invoice("css@novogene-amea.com","css@novogene-amea.com","finance.css@novogeneait.sg, taehoon.kim@novogene.com")[0],
                         "DIRECT_CSS_PENDING_OWNER_MATCH")
    def test_reply_to_not_owner(self):
        self.assertEqual(classify_mail("hyunseok.koo@novogene.com","ns@n-s.co.kr","sales.korea@novogene-amea.com","taehoon.kim@novogene.com"),"SHARED_OR_OTHER_PERSON_MAIL")
    def test_owner_override(self):
        self.assertEqual(classify_invoice("hyunseok.koo@novogene.com","ns@n-s.co.kr","sales.korea@novogene-amea.com",known_owner=True)[0],"OWNER_VERIFIED")

if __name__ == "__main__":
    unittest.main()
