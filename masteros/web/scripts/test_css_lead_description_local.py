#!/usr/bin/env python3
"""Description audit uses ALL SFDC Lead rows, not truncated sent-only history."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import css_mail_local as m
from test_css_mail_local import sheet_data,OWNER,NOW

def raw(description="Original inquiry: mRNA 12 samples"):
    head=[""]*23
    head[12]="Description";head[14]="Email";head[22]="SFDC Lead ID"
    row=[""]*23
    row[12]=description;row[14]="person@uni.ac.kr";row[22]="Lead-1"
    return [head,row]

class DescriptionTests(unittest.TestCase):
    def test_exact_lead_id_email_join_preserves_inquiry_content(self):
        result=m.snapshot(*sheet_data(),OWNER,NOW,raw_leads=raw())
        self.assertEqual(result["leadDescriptionSourceStatus"],"VERIFIED")
        lead=result["leads"][0]
        self.assertEqual(lead["descriptionClass"],"DESCRIPTION_PRESENT")
        self.assertIn("mRNA",lead["description"])
        self.assertEqual(result["leadDescriptions"]["DESCRIPTION_PRESENT"],1)
        self.assertEqual(lead["created"],"11/10/2026")
        self.assertEqual(lead["lastEver"],"")
    def test_empty_description_is_generic_mail_candidate_not_sending(self):
        result=m.snapshot(*sheet_data(),OWNER,NOW,raw_leads=raw("   "))
        self.assertEqual(result["leads"][0]["descriptionClass"],"DESCRIPTION_EMPTY")
        self.assertEqual(result["leadDescriptions"]["DESCRIPTION_EMPTY"],1)
        self.assertEqual(result["leads"][0]["evidence"],"NO_PERSONAL_OUTBOUND_EVIDENCE")
    def test_missing_or_misidentified_lead_is_not_classified_as_blank(self):
        sample=raw("Inquiry")
        sample[1][14]="wrong@uni.ac.kr"
        with self.assertRaisesRegex(ValueError,"EMAIL_LINK_MISMATCH"):
            m.snapshot(*sheet_data(),OWNER,NOW,raw_leads=sample)
        sample=raw("Inquiry")
        sample[1][22]="Other-Lead"
        with self.assertRaisesRegex(ValueError,"ID_COVERAGE_MISMATCH"):
            m.snapshot(*sheet_data(),OWNER,NOW,raw_leads=sample)
    def test_duplicate_lead_and_schema_changes_are_blocked(self):
        sample=raw()
        with self.assertRaisesRegex(ValueError,"DUPLICATE_ID"):
            m.snapshot(*sheet_data(),OWNER,NOW,raw_leads=sample+[sample[1]])
        sample=raw();sample[0][12]="Not Description"
        with self.assertRaisesRegex(ValueError,"SCHEMA_MISMATCH"):
            m.snapshot(*sheet_data(),OWNER,NOW,raw_leads=sample)

if __name__=="__main__":unittest.main()
