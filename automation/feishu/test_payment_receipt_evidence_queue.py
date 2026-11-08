#!/usr/bin/env python3
"""Credential-free receipt evidence queue tests; no customer rows and no writes."""
import unittest
from payment_receipt_evidence_queue import (
    HEAD, parse_day, source_snapshot, build, assert_existing_qc,
)

INVOICE_HEAD=[
    "Invoice Number","Quotation ID","SFDC Quote ID","AMEA Project ID",
    "Institution","Invoice Date","Invoice Amount (KRW)",
]
RECEIPT_HEAD=[
    "Deposit Date","Customer Name","Amount (KRW)","CMS No.","Column 5",
    "Date","CMS No. [2]","Amount","Column 9","Date [2]",
    "Customer Name [2]","Amount [2]","CMS No. [3]",
]
OUTSTANDING_HEAD=[
    "Customer Name","ERP Invoice Number","Contact Person","Invoice Type",
    "PO Number","Project Number","CMS Invoice Number",
]
MANIFEST_HEAD=[
    "Source","Source Date","Synced At KST","Source ID",
    "Rows","Schema","Meaning",
]

def invoice(num, amount=1100, issued="2026-10-01"):
    return [num,"AMEA2026100101","","AMEA2026100101",
            "Synthetic",issued,"%s KRW" % amount]

def source(values):
    return [
        MANIFEST_HEAD,
        ["Payment Receipt","2026-10-31","2026-11-08T22:37:29+09:00",
         "synthetic",str(len(values)-1),"HEADER_MATCHED","Review"],
    ]

def rec(date=None, amount=None, number=None,
        date2=None, amount2=None, number2=None,
        date3=None, amount3=None, number3=None):
    row=[""]*13
    for di,ai,ci,d,a,n in [
        (0,2,3,date,amount,number),
        (5,7,6,date2,amount2,number2),
        (9,11,12,date3,amount3,number3),
    ]:
        row[di]=d or ""
        row[ai]=a if a is not None else ""
        row[ci]=n or ""
    return row

class ReceiptQueueTests(unittest.TestCase):
    def data(self):
        ids=["209126%06d" % x for x in range(101,114)]
        invoices=[INVOICE_HEAD]+[invoice(v) for v in ids]
        invoices[7][5]="2026-10-15"  # Pre-issuance receipt
        invoices[13][5]=""          # Issue date not available
        receipts=[
            RECEIPT_HEAD,
            rec("2026-10-20",1100,ids[0],
                "2026-10-20",2200,ids[1]+", "+ids[2],
                "2026-10-20",1100,ids[3]),
            rec("2026-10-21",1100,ids[3],
                "2026-10-22",1000,ids[4],
                "2026-09-01",1100,ids[6]),
            rec("2026-10-22",1100,ids[7],
                "2026-11-01",1100,ids[8],
                "2026-10-23",1100,ids[9]+"-01"),
            rec("",1100,ids[10],
                "2026-10-24","",ids[11],
                "2026-10-24",1100,ids[12]),
        ]
        outstanding=[
            OUTSTANDING_HEAD,
            ["","","","","","","209126000108"],
        ]
        return invoices,receipts,outstanding,source(receipts)

    def test_source_snapshot_and_date_formats(self):
        self.assertEqual(parse_day("2026-10-31").isoformat(),"2026-10-31")
        self.assertEqual(parse_day("27-Apr-26").isoformat(),"2026-04-27")
        self.assertEqual(parse_day("1-June-2026").isoformat(),"2026-06-01")
        self.assertEqual(parse_day("45980").isoformat(),"2025-11-19")
        a=self.data()
        self.assertEqual(source_snapshot(a[3],a[1]).isoformat(),"2026-10-31")
        broken=source(a[1]);broken[1][4]="9999"
        with self.assertRaisesRegex(RuntimeError,"RECEIPT_MANIFEST_ROW_PARITY_FAILED"):
            source_snapshot(broken,a[1])

    def test_all_classes_and_no_paid_inference(self):
        rows,counts=build(*self.data())
        self.assertEqual(rows[0],HEAD)
        self.assertEqual(len(rows),14)
        actual={r[0]:r for r in rows[1:]}
        def status(i):
            return actual["209126%06d" % i][9]
        self.assertEqual(status(101),"EXACT_AMOUNT_DATE_RECEIPT_CANDIDATE")
        self.assertEqual(status(102),"GROUPED_ALLOCATION_REVIEW")
        self.assertEqual(status(103),"GROUPED_ALLOCATION_REVIEW")
        self.assertEqual(status(104),"DUPLICATE_REFERENCE_REVIEW")
        self.assertEqual(status(105),"RECEIPT_AMOUNT_MISMATCH_REVIEW")
        self.assertEqual(status(106),"NO_RECEIPT_REFERENCE")
        self.assertEqual(status(107),"RECEIPT_BEFORE_ISSUANCE_REVIEW")
        self.assertEqual(status(108),"RECEIPT_OUTSTANDING_CONFLICT_REVIEW")
        self.assertEqual(status(109),"RECEIPT_AFTER_SNAPSHOT_REVIEW")
        self.assertEqual(status(110),"RECEIPT_CMS_SUFFIX_REVIEW")
        self.assertEqual(status(111),"RECEIPT_DATE_MISSING_REVIEW")
        self.assertEqual(status(112),"RECEIPT_AMOUNT_MISSING_REVIEW")
        self.assertEqual(status(113),"RECEIPT_DATE_MISSING_REVIEW")
        self.assertEqual(sum(counts.values()),13)
        self.assertTrue(all(row[12]=="OWNER_NOT_VERIFIED" and row[13]=="UNKNOWN"
                            for row in rows[1:]))
        self.assertEqual(actual["209126000108"][11],"YES")

    def test_suffixed_cms_with_amount_mismatch_is_amount_review(self):
        invoices,receipts,outstanding,manifest=self.data()
        invoices.append(invoice("209126000114",amount=1100))
        receipts.append(rec("2026-10-25",900,"209126000114-01"))
        manifest=source(receipts)
        rows,counts=build(invoices,receipts,outstanding,manifest)
        entry=next(row for row in rows[1:] if row[0]=="209126000114")
        self.assertEqual(entry[9],"RECEIPT_AMOUNT_MISMATCH_REVIEW")
        self.assertEqual(counts["RECEIPT_AMOUNT_MISMATCH_REVIEW"],2)
        self.assertEqual(entry[13],"UNKNOWN")

    def test_qc_crosscheck_fail_closed(self):
        rows,counts=build(*self.data())
        qc=[
            ["Invoice records",13],["Receipt linked invoice IDs",11],
            ["Receipt single-ID exact-amount candidates",1],
            ["Receipt grouped-allocation review",2],
            ["Receipt duplicate-ID review",1],
            ["Receipt amount mismatch review",1],
            ["Invoice-level verified paid count","UNKNOWN"],
        ]
        # This synthetic input includes additional date/cross-source exceptions,
        # so production parity intentionally remains fail-closed.
        with self.assertRaisesRegex(RuntimeError,"EXISTING_RECEIPT_QC_PARITY_FAILED"):
            assert_existing_qc(qc,rows,counts)
        for row in qc:
            if row[0]=="Receipt linked invoice IDs":
                row[1]=12
        self.assertEqual(counts["NO_RECEIPT_REFERENCE"],1)
        qc[-1][1]="1"
        with self.assertRaisesRegex(RuntimeError,"PAID_STATUS_NOT_PROVEN"):
            # Parity must pass before checking forbidden paid promotion.
            qc[2][1]=counts["EXACT_AMOUNT_DATE_RECEIPT_CANDIDATE"]
            qc[3][1]=counts["GROUPED_ALLOCATION_REVIEW"]
            qc[4][1]=counts["DUPLICATE_REFERENCE_REVIEW"]
            qc[5][1]=counts["RECEIPT_AMOUNT_MISMATCH_REVIEW"]
            assert_existing_qc(qc,rows,counts)

if __name__=="__main__":
    unittest.main()
