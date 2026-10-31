import datetime as dt
import unittest
from css_parallel_audit import audit_lead,audit_revenue,KST

NOW=dt.datetime(2026,10,29,23,30,tzinfo=KST)


class ParallelAuditTests(unittest.TestCase):
    def lead_data(self):
        report=[["Entity","","","","","","","",""],
                ["Leads","2026-10-29 12:00:03 KST","2026-10-29 12:05:00 KST","493","493","0","0","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","STAGED_NOT_PROMOTED"],
                ["Opportunities","2026-10-29 12:00:08 KST","2026-10-29 12:05:00 KST","700","700","0","0","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","STAGED_NOT_PROMOTED"],
                ["Quotation","2026-10-29 12:00:14 KST","2026-10-29 12:05:00 KST","3794","818","0","0","cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","STAGED_NOT_PROMOTED"]]
        head=[""]*23;head[22]="SFDC Lead ID"
        raw=[head]
        ph=[""]*20;ph[0]="Lead ID";ph[14]="My Mail Status"
        personal=[ph]
        pool=[["","","","Source","Record ID","","","","","","","Verification"]]
        for i in range(493):
            raw.append([""]*22+["L"+str(i)])
            row=[""]*20;row[0]="L"+str(i);row[14]=(
                "SENT_AFTER_LEAD_CONFIRMED" if i<235 else
                "SENT_BEFORE_LEAD_ONLY" if i<244 else
                "NO_PERSONAL_OUTBOUND_EVIDENCE")
            row[18]="2026-10-29T18:45:01+09:00";row[7]="New"
            personal.append(row)
            if i>=235:
                p=[""]*14;p[3]="LEAD";p[4]=row[0];p[11]=row[14]
                pool.append(p)
        return report,raw,personal,pool,[["Metric","Value"],["Lead records","478"]]

    def test_lead_parity_and_legacy_warning(self):
        r=audit_lead(*self.lead_data(),NOW)
        self.assertEqual(r["no_personal_outbound"],249)
        self.assertEqual(r["nba_leads"],258)
        self.assertEqual(r["result"],"PASS_WITH_REVIEW")

    def test_live_four_column_analytics_uses_latest_not_legacy_pilot(self):
        d=list(self.lead_data())
        d[4]=[
            ["SFDC 3-REPORT ANALYTICS","Live formulas from imported pilot"],
            ["Metric","Pilot (legacy)","Latest QQ staged","Difference (latest - pilot)"],
            ["Lead records","478","493","15"],
            ["Opportunity records","693","700","7"],
            ["Unique quotation IDs","805","818","13"],
            ["Quotation process rows","3741","3794","53"],
        ]
        self.assertEqual(audit_lead(*d,NOW)["result"],"PASS")
        # A frozen historical 478 is not a reason to label latest as stale.

    def test_live_analytics_mismatch_blocks_instead_of_falsely_passing(self):
        d=list(self.lead_data())
        d[4]=[
            ["SFDC 3-REPORT ANALYTICS","Live formulas from imported pilot"],
            ["Metric","Pilot (legacy)","Latest QQ staged","Difference (latest - pilot)"],
            ["Lead records","478","478","0"],
            ["Opportunity records","693","700","7"],
            ["Unique quotation IDs","805","818","13"],
            ["Quotation process rows","3741","3794","53"],
        ]
        with self.assertRaisesRegex(ValueError,"latest differs"):
            audit_lead(*d,NOW)

    def test_preserved_no_new_report_accepted_with_fresh_source(self):
        d=list(self.lead_data())
        for r in d[0][1:]:
            r[8]="PRESERVED_NO_NEW_REPORT"
        self.assertEqual(audit_lead(*d,NOW)["result"],"PASS_WITH_REVIEW")

    def test_preserved_without_hash_is_not_verified(self):
        d=list(self.lead_data())
        d[0][1][8]="PRESERVED_NO_NEW_REPORT"
        d[0][1][7]=""
        with self.assertRaisesRegex(ValueError,"staging evidence invalid"):
            audit_lead(*d,NOW)

    def test_lead_fails_if_sent_requeued(self):
        d=list(self.lead_data())
        row=[""]*14;row[3]="LEAD";row[4]="L0";row[11]="SENT_AFTER_LEAD_CONFIRMED"
        d[3].append(row)
        with self.assertRaisesRegex(ValueError,"mismatch|contacted"):
            audit_lead(*d,NOW)

    def revenue_data(self):
        h=["Month"]+[""]*16
        r=[""]*17;r[0]="2026-10";r[1]="₩82,137,000";r[2]="₩67,743,500"
        r[3]="₩21,152,370";r[6]="2";r[9]="1";r[11]="2026-10-29 18:53:45 KST"
        r[12]="149880500";r[15]="99.920"
        lead=[""]*20;lead[14]="Statement ID"
        s1=[""]*20;s1[5]="67000000";s1[7]="";s1[11]="PENDING_VERIFIED_NOT_ACTUAL"
        s1[14]="J001-X000-Z01";s1[16]="AUTO_ISSUE_OVERDUE_REVIEW"
        s2=[""]*20;s2[5]="743500";s2[11]="PENDING_VERIFIED_NOT_ACTUAL"
        s2[14]="J002-X000-Z01";s2[16]="AUTO_ISSUE_SCHEDULED"
        fx=[["Setting","Value"],["Reporting FX KRW per USD","1500"]]
        return [h,r],[lead,s1,s2],fx

    def test_revenue_parity_and_overdue_flag(self):
        r=audit_revenue(*self.revenue_data(),NOW)
        self.assertEqual(r["verified_billing_krw"],149880500)
        self.assertEqual(r["overdue_review"],1)

    def test_revenue_duplicate_installment_fails(self):
        d=list(self.revenue_data())
        d[1][2][14]=d[1][1][14]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            audit_revenue(*d,NOW)

if __name__=="__main__":
    unittest.main()
