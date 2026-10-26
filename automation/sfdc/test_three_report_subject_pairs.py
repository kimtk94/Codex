#!/usr/bin/env python3
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from three_report_subject_pairs import build, normalize_subject
class Tests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_subject("Re: FW: [Novogene] Quote followup"),"[novogene] quote followup")
    def test_direction_contact_and_shared_ambiguity(self):
        queue=[["Opportunity ID","Institution","Stage","Quote IDs"],
               ["O1","Univ","Negotiation","Q1"],
               ["O2","Univ","PO Received","Q2"]]
        quotes=[["SFDC Quotation ID","Email"],["Q1","customer@example.edu"],
                ["Q2","customer@example.edu"]]
        def mail(frm,to,subject,date):
            return [date,"",frm,to,"","",subject]
        emails=[
            mail("taehoon.kim@novogene.com","customer@example.edu","[Novogene] Project sequencing","2026-10-20T10:00:00+09:00"),
            mail("customer@example.edu","taehoon.kim@novogene.com","Re: [Novogene] Project sequencing","2026-10-21T10:00:00+09:00"),
            mail("unrelated@example.edu","taehoon.kim@novogene.com","Re: [Novogene] Project sequencing","2026-10-22T10:00:00+09:00")]
        result=build(queue,quotes,emails,"now")
        self.assertEqual(len(result)-1,2)
        for row in result[1:]:
            self.assertEqual(row[5],1)
            self.assertEqual(row[6],1)
            self.assertEqual(row[9],"SHARED_EMAIL_AMBIGUOUS")
if __name__=="__main__": unittest.main()
