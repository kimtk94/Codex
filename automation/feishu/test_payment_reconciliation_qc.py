#!/usr/bin/env python3
"""Synthetic, no-network checks of project reconciliation constraints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from payment_reconciliation_qc import analyze, mapping, audit_receipt_candidates

def main():
    invoices = [["Invoice Number"], ["209126000964"], ["209126000963"]]
    feishu = [["Project ID", "Tax invoice unissued", "Payment outstanding"],
              ["X209SC26088039", "NO", "YES"], ["X209SC26096779", "YES", "NO"]]
    pairs, conflicts = mapping([["X", "H", "Status", "Evidence"],
                                ["X209SC26088039", "H209SC26088039", "VERIFIED", "Invoice 209126000964"],
                                ["X209SC26096779", "H209SC26096779", "UNVERIFIED", ""]])
    assert conflicts == 0 and pairs == {"X209SC26088039": "H209SC26088039"}
    stats, _, _ = analyze(invoices, feishu, [])
    assert stats["INVOICES"] == 2 and stats["OUTSTANDING_FLAG_PROJECTS"] == 1
    assert stats["VERIFIED_X_TO_H_BRIDGES"] == 0
    # Different ID namespaces are NOT interchangeable without explicit evidence.
    stats2, _, _ = analyze(invoices, feishu, [["X", "H", "Status", "Evidence"],
                         ["X209SC26088039", "H209SC26088039", "VERIFIED", "Document ID"],
                         ["X209SC26088039", "H209SC26012345", "VERIFIED", "Conflicting document"]])
    assert stats2["BRIDGE_CONFLICTS"] == 1 and stats2["VERIFIED_X_TO_H_BRIDGES"] == 0
    # Three side-by-side receipt tables: date, amount and CMS IDs must not
    # be read from the same column offset across all sections.
    receipts=[["Deposit Date","Customer Name","Amount (KRW)","CMS No.","Column 5",
               "Date","CMS No. [2]","Amount","Column 9","Date [2]",
               "Customer Name [2]","Amount [2]","CMS No. [3]"],
              ["45980","",1100,"209126000101",None,"8-Nov-26",
               "209126000102, 209126000103",3000,None,
               "2026-11-08","",900,"209126000104"],
              ["45980","",500,"209126000105",None,"2026-11-08",
               "209126000106",2000,None,"2026-11-08","",0,"209126000101"]]
    amounts={"209126000101":1100,"209126000102":1000,
             "209126000103":2000,"209126000104":900,
             "209126000105":800,"209126000106":2000}
    candidates=audit_receipt_candidates(receipts,amounts)
    assert candidates["RECEIPT_LINKED_INVOICE_IDS"]==6
    assert candidates["RECEIPT_DUPLICATE_REFERENCE_REVIEW"]==1
    assert candidates["RECEIPT_GROUPED_ALLOCATION_REVIEW"]==2
    assert candidates["RECEIPT_AMOUNT_MISMATCH_REVIEW"]==1
    assert candidates["RECEIPT_EXACT_AMOUNT_CANDIDATE"]==2
    bad=[row[:] for row in receipts]
    bad[0][12]="WRONG CMS COLUMN"
    try:
        audit_receipt_candidates(bad,amounts)
        assert False, "Expected source-schema fail closed"
    except RuntimeError as e:
        assert str(e)=="RECEIPT_SOURCE_HEADER_CHANGED"
    print("PAYMENT_RECONCILIATION_OFFLINE_TESTS_PASS")

if __name__ == "__main__":
    main()
