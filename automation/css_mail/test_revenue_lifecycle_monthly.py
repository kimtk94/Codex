"""Offline reconciliation: Actual + verified open Statements + unmatched Forecast."""
import datetime as dt
import unittest
from revenue_lifecycle_monthly import compute

def invoice(number,amount):
    return [number,str(amount),"AMEA2026092127","H209SC260910566","SQ",
            "TAX INVOICE-"+number+"-H209SC260910566-SQ-AMEA2026092127-KRW"+str(amount)+".00.pdf",
            "❗️Notice: Invoice Issued & Statement Confirmed – J001-X209SC260910566-Z01 -"+number+
            " - H209SC260910566 - AMEA2026092127",
            "2026-10-28T12:00:00+08:00","40000","INBOX|1776302013|40000",
            "FILENAME_PARSED","2026-10-28T13:00:00+00:00"]

def project(x,billing,estimate=0,open_j="",pending="",verified="NO_OPEN_STATEMENT"):
    r=[""]*24
    r[0]=x
    r[12]="2026-10"
    r[16]=billing;r[17]=estimate;r[20]=open_j;r[22]=pending;r[23]=verified
    return r

class RevenueLifecycleTests(unittest.TestCase):
    def test_three_way_without_issued_forecast_duplicate(self):
        iv=[["invoice_number"],invoice("209126000989",1320000)]
        life=[["Project / Sub-project"],
              project("X209SC260910566-Z01","ISSUED (BALANCE UNVERIFIED)",estimate=2000000),
              project("X209SC260910567-Z01","STATEMENT READY - INVOICE PENDING",
                      estimate=300000,open_j="J001",pending=220000,verified="AMOUNT_VERIFIED 1/1"),
              project("X209SC260910568-Z01","PROJECT FORECAST",estimate=500000),
              project("X209SC260910569-Z01","BLOCKED / EXCLUDED FROM FORECAST",estimate=600000)]
        out=compute(iv,life,dt.datetime(2026,10,29,tzinfo=dt.timezone.utc))
        oct_row=next(x for x in out[1:] if x[0]=="2026-10")
        self.assertEqual(oct_row[1:5],[1320000,220000,500000,2040000])
        self.assertEqual(oct_row[5:10],[1,1,0,1,0])

    def test_unverified_statement_amount_is_not_assumed_zero_revenue(self):
        life=[["Project / Sub-project"],
              project("X209SC260910567-Z01","STATEMENT READY - INVOICE PENDING",
                      estimate=300000,open_j="J001",pending="",verified="AMOUNT_VERIFIED 0/1")]
        out=compute([["invoice_number"]],life,dt.datetime(2026,10,29,tzinfo=dt.timezone.utc))
        row=out[1]
        self.assertEqual(row[2],0)
        self.assertEqual(row[7],1)
        self.assertEqual(row[10],"PENDING_AMOUNTS_UNVERIFIED")

    def test_october_statement_not_misclassified_as_december_pending(self):
        life = [["Project / Sub-project"],
                project("X209SC26065705-Z01",
                        "ISSUED + STATEMENT PENDING",
                        open_j="J002", pending="22704000",
                        verified="AMOUNT_VERIFIED 1/1")]
        life[1][12] = "2026-12"  # Feishu estimated completion month
        life[1][21] = "2026-10-26T15:22:52+08:00"  # Original J002 notice
        out = compute([["invoice_number"]], life,
                      dt.datetime(2026, 10, 29, tzinfo=dt.timezone.utc))
        oct_row = next(r for r in out[1:] if r[0] == "2026-10")
        self.assertEqual(oct_row[2], 22704000)
        self.assertEqual(oct_row[6], 1)
        self.assertFalse(any(r[0] == "2026-12" and r[2] for r in out[1:]))

    def test_invoice_number_conflict_fails_closed(self):
        inv=[["invoice_number"],invoice("209126000989",1320000),invoice("209126000989",1320000)]
        inv[2][7]="2026-11-04T12:00:00+08:00"
        with self.assertRaises(RuntimeError):
            compute(inv,[["Project / Sub-project"]],dt.datetime(2026,10,29,tzinfo=dt.timezone.utc))

if __name__=="__main__":
    unittest.main()
