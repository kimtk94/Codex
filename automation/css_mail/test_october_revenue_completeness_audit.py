#!/usr/bin/env python3
"""Read-only October revenue scope: no manual eTax or unowned gap autopublish."""
import unittest

from october_revenue_completeness_audit import (
    audit,qq_original_october,net_won,etax_evidence,
)


def qq_row(invoice,gross,month="2026-10-30",project="X209SC26095539-Z01",ameax="AMEA2026091512"):
    h="H"+project[1:project.index("-")]
    r=[""]*12
    r[0]=invoice
    r[1]=str(gross)
    r[2]=ameax
    r[3]=h
    r[5]=f"TAX INVOICE-{invoice}-{h}-SQ-{ameax}-KRW{gross}.00.pdf"
    r[6]=f"❗️Notice: Invoice Issued & Statement Confirmed – J001-{project} -{invoice}"
    r[7]=month+"T16:00:21+08:00"
    r[8]="41036"
    r[9]="INBOX|1776302013|41036"
    r[10]="FILENAME_PARSED"
    return r


def etax_row(erp,cms,gross,gl,project="X209SC26095539",source="开票导入",sales="Kim Taehoon"):
    r=[""]*26
    r[2]=source;r[4]=erp;r[5]=cms;r[9]=project
    r[15]=str(gross);r[16]=str(gl);r[25]=sales
    return r


def examples():
    qq=[["invoice_number"]]+[
        qq_row("209126001032",4526500),
        qq_row("209126001037",2453000,project="X209SC26095540-Z01",ameax="AMEA2026091513"),
    ]
    etax=[["","","","","ERP Invoice Number"]+[""]*20+["Sales"]]+[
        etax_row("209102365","209126001037",2453000,46325,project="X209SC26095540"),
        etax_row("20910000197","",4526500,46183,source="Manual Invoice"),
        etax_row("20910000203","",28567000,46314,project="X209SC26104320",source="Manual Invoice"),
        etax_row("20910000208","",1287000,46317,project="X209SC26107211",source="Manual Invoice"),
        etax_row("20910000209","",9317000,46317,project="X209SC26107211",source="Manual Invoice"),
        etax_row("20910000204","",4366450,46316,project="X209SC26099999",source="Manual Invoice",sales="Other"),
    ]
    gap=[["Invoice Number"]]+[
        ["209126000887","2026-10","12012000"],
        ["209126001037","2026-10","2453000"],
        ["209126000984","2026-10","4438500"],
    ]
    return qq,etax,gap


class RevenueAuditTests(unittest.TestCase):
    def test_manual_candidate_three_and_cross_source_overlap(self):
        source=examples()
        found=audit(*source)
        self.assertEqual(found["status"],"REVIEW_REQUIRED")
        self.assertEqual((found["qq_count"],found["qq_gross"]),
                         (2,6979500))
        self.assertEqual(found["etax_qq_exact_match"],1)
        self.assertEqual(found["etax_qq_unmatched"],["209126001032"])
        self.assertEqual(found["manual_candidate_count"],3)
        self.assertEqual(found["manual_candidate_gross"],39171000)
        self.assertEqual(found["manual_candidate_net"],35610000)
        self.assertEqual(found["manual_erp_ids"],
                         ["20910000203","20910000208","20910000209"])
        self.assertEqual(found["gap_candidate_count"],2)
        self.assertEqual(found["gap_candidate_gross"],16450500)
        self.assertEqual(len(found["possible_double"]),1)
        self.assertEqual(found["possible_double"][0]["erp"],"20910000197")
        self.assertEqual(found["possible_double"][0]["qq_invoice"],"209126001032")
        self.assertEqual(found["hypothetical_if_manual_verified_net"],
                         found["qq_net"]+35610000)

    def test_qq_amount_is_checked_against_original_attachment(self):
        qq,etax,gap=examples()
        qq[1][1]="4526501"
        with self.assertRaisesRegex(ValueError,"QQ_GROSS_OR_UID_CONFLICT"):
            audit(qq,etax,gap)

    def test_reply_and_bad_invoice_do_not_inflate(self):
        qq,etax,gap=examples()
        reply=list(qq[1])
        reply[6]="Re: "+reply[6]
        qq.append(reply)
        self.assertEqual(audit(qq,etax,gap)["qq_count"],2)

    def test_different_erp_sales_label_not_pushed_into_personal(self):
        qq,etax,gap=examples()
        etax.append(etax_row("20910000999","",20000000,46315,
                             source="Manual Invoice",sales="Other"))
        self.assertEqual(audit(qq,etax,gap)["manual_candidate_gross"],39171000)

    def test_vat_rounding_per_invoice_not_aggregate_shortcut(self):
        self.assertEqual(net_won(11),10)
        self.assertEqual(net_won(222750),202500)
        self.assertEqual(net_won(8712000),7920000)
        self.assertEqual(net_won(28567000),25970000)
        self.assertEqual(net_won(1287000)+net_won(9317000),9640000)


if __name__=="__main__":
    unittest.main()
