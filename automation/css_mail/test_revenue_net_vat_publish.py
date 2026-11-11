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

    def test_november_six_original_invoices_reconcile_exactly(self):
        # Live 11/08 source audit: 4 invoices received 11/04 plus 2 on 11/06.
        records=[
            ("209126001054",1287000,"2026-11-04T12:33:57+09:00"),
            ("209126001053",1721500,"2026-11-04T12:13:17+09:00"),
            ("209126001051",665500,"2026-11-04T11:11:16+09:00"),
            ("209126001058",34587300,"2026-11-04T16:01:08+09:00"),
            ("209126001072",222750,"2026-11-06T09:07:52+09:00"),
            ("209126001077",8712000,"2026-11-06T17:46:05+09:00"),
        ]
        invoices=[["invoice_number"]]
        for i,(number,amount,date) in enumerate(records):
            item=invoice(number,amount,date)
            item[8]=str(50000+i)
            item[9]="INBOX|1776302013|"+str(50000+i)
            invoices.append(item)
        header=["Month","Actual Invoice KRW","Pending Verified KRW",
                "Forecast KRW","Combined KRW (verified + estimate)",
                "Invoice Count"]
        ledger=[header,
                ["2026-10","0","0","0","0","0"],
                ["2026-11","47196050","18429400","43767645",
                 "109393095","6"]]
        rows=build(invoices,ledger,NOW)
        nov=next(r for r in rows[1:] if r[0]=="2026-11")
        self.assertEqual((nov[1],nov[2],nov[4]),(47196050,42905500,6))
        self.assertEqual(nov[5:7],[18429400,43767645])
        # A lifecycle snapshot with four invoices cannot certify six.
        ledger[-1][1]="38261300"
        ledger[-1][5]="4"
        with self.assertRaisesRegex(ValueError,"PARITY_FAILED_2026-11"):
            build(invoices,ledger,NOW)

    def test_missing_november_lifecycle_never_silently_drops_issued_invoices(self):
        records=[["invoice_number"],
                 invoice("209126001072",222750,"2026-11-06T09:07:52+09:00")]
        ledger=[["Month","Actual Invoice KRW","Pending Verified KRW",
                 "Forecast KRW","Combined KRW (verified + estimate)",
                 "Invoice Count"],month(0,0)]
        with self.assertRaisesRegex(ValueError,"NOT_IN_LIFECYCLE"):
            build(records,ledger,NOW)

    def test_unknown_open_statement_does_not_block_verified_tax_invoice(self):
        inv=[["invoice_number"],invoice("209126001012",1622500)]
        row=month(1622500,1,pending=0,forecast=0)
        row[6]="1"   # one open Statement, unverified amount
        row[7]="1"   # unknown must never become issued Revenue
        ledger=[["Month","Actual Invoice KRW","Pending Verified KRW",
                 "Forecast KRW","Combined KRW (verified + estimate)",
                 "Invoice Count","Open Statement Count","Pending Amount Unknown"],row]
        out=build(inv,ledger,NOW)[1]
        self.assertEqual((out[1],out[2],out[4],out[5]),(1622500,1475000,1,0))
        row[7]="-1"
        with self.assertRaisesRegex(ValueError,"NEGATIVE_UNVERIFIED_PENDING_COUNT"):
            build(inv,ledger,NOW)

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
