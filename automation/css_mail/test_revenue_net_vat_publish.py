"""No-credential VAT-excluded invoice evidence and fail-closed tests."""
import datetime as dt
import unittest
from revenue_net_vat_publish import build, net_won

NOW=dt.datetime(2026,10,30,18,30,tzinfo=dt.timezone(dt.timedelta(hours=9)))

def invoice(number, amount, date="2026-10-28T12:00:00+08:00"):
    return [number,str(amount),"AMEA2026100213","H209SC26100560","SQ",
            "TAX INVOICE-"+number+"-H209SC26100560-SQ-AMEA2026100213-KRW"+str(amount)+".00.pdf",
            "❗️Notice: Invoice Issued & Statement Confirmed – J001-X209SC26100560-Z01 -"+number,
            date,"40600","INBOX|1776302013|40600","FILENAME_PARSED",
            "2026-10-28T09:00:00+00:00"]

def month(gross,count,pending=0,forecast=21152370):
    return ["2026-10",str(gross),str(pending),str(forecast),
            str(gross+pending+forecast),str(count),"0","0","7","0",
            "INVOICES_VERIFIED_FORECAST_ESTIMATED","2026-10-30 18:23:12 KST"]

class VatEvidenceTests(unittest.TestCase):
    def test_per_invoice_vat_exclusion_and_separate_forecast(self):
        inv=[["invoice_number"],invoice("209126001012",1622500),
             invoice("209126001010",973500)]
        ledger=[["Month","Actual Invoice KRW","Pending Verified KRW",
                 "Forecast KRW","Combined KRW (verified + estimate)","Invoice Count"],
                month(2596000,2)]
        r=build(inv,ledger,NOW)[1]
        self.assertEqual(r[1],2596000)
        self.assertEqual(r[2],net_won(1622500)+net_won(973500))
        self.assertEqual(r[4],2)
        self.assertEqual(r[5],0)
        self.assertEqual(r[6],21152370)

    def test_vat_rounded_per_invoice(self):
        self.assertEqual(net_won(4438500),4035000)
        self.assertEqual(net_won(11),10)

    def test_duplicate_and_reply_do_not_inflate_invoice(self):
        original=invoice("209126001012",1622500)
        reply=invoice("209126001012",1622500)
        reply[6]="Re: "+reply[6]
        data=[["invoice_number"],original,reply,original]
        ledger=[["Month","Actual Invoice KRW","Pending Verified KRW",
                 "Forecast KRW","Combined KRW (verified + estimate)","Invoice Count"],
                month(1622500,1)]
        self.assertEqual(build(data,ledger,NOW)[1][4],1)

    def test_mismatched_invoice_fails_closed(self):
        inv=[["invoice_number"],invoice("209126001012",1622500)]
        ledger=[["Month","Actual Invoice KRW","Pending Verified KRW",
                 "Forecast KRW","Combined KRW (verified + estimate)","Invoice Count"],
                month(1622499,1)]
        with self.assertRaisesRegex(ValueError,"PARITY"):
            build(inv,ledger,NOW)

    def test_filename_amount_conflict_fails_closed(self):
        bad=invoice("209126001012",1622500);bad[1]="1622511"
        ledger=[["Month","Actual Invoice KRW","Pending Verified KRW",
                 "Forecast KRW","Combined KRW (verified + estimate)","Invoice Count"],
                month(1622511,1)]
        with self.assertRaisesRegex(ValueError,"MISMATCH"):
            build([["invoice_number"],bad],ledger,NOW)

if __name__=="__main__":
    unittest.main()
