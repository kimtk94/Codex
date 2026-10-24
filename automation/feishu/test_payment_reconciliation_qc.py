#!/usr/bin/env python3
"""Synthetic, no-network checks of project reconciliation constraints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from payment_reconciliation_qc import analyze, mapping

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
    print("PAYMENT_RECONCILIATION_OFFLINE_TESTS_PASS")

if __name__ == "__main__":
    main()
