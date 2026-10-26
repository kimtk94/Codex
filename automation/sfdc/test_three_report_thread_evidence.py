#!/usr/bin/env python3
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from three_report_thread_evidence import build

class ExactThreadTests(unittest.TestCase):
    def test_subject_id_and_contact_are_both_required(self):
        queue=[["Opportunity ID","Institution","Stage","Quote IDs","Opportunity Name"],
               ["Opp-2026-10-20-123","Univ","Negotiation","QID-2026-10-20-456","Project A"],
               ["Opp-2026-10-21-124","Univ2","Quotation Issued","QID-2026-10-21-457","Project B"]]
        quote=[["SFDC Quotation ID","Email"],["QID-2026-10-20-456","customer@univ.edu"],
               ["QID-2026-10-21-457","second@univ.edu"]]
        def mail(frm,to,subj):
            return ["2026-10-26T10:00:00+09:00","",""+frm,to,"","",subj]
        messages=[
            mail("taehoon.kim@novogene.com","customer@univ.edu","Re: QID-2026-10-20-456"),
            mail("customer@univ.edu","taehoon.kim@novogene.com","Re: Opp-2026-10-20-123"),
            mail("other@univ.edu","taehoon.kim@novogene.com","Re: QID-2026-10-20-456"),
            mail("taehoon.kim@novogene.com","second@univ.edu","Re: QID-2026-10-20-456"),
            mail("second@univ.edu","taehoon.kim@novogene.com","Unrelated inquiry")]
        result,scanned=build(queue,quote,messages,"now")
        self.assertEqual(scanned,5)
        self.assertEqual(result[1][4:6],[1,1])
        self.assertEqual(result[2][4:6],[0,0])
        self.assertEqual(result[2][7],"NO_EXACT_ID_MATCH_NOT_UNANSWERED")
if __name__=="__main__": unittest.main()
