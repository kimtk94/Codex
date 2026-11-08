#!/usr/bin/env python3
"""Offline regression tests for authoritative monthly VAT-excluded Revenue."""
import copy
import unittest
from monthly_revenue_canonical import evidence_rows,RevenueEvidenceError


def source():
    net=[]
    life=[]
    auth=[]
    for month,count,gross,amount in [
            ("2026-10",48,158541900,144129000),
            ("2026-11",4,38261300,34783000)]:
        net.append({
            "Month":month,"Issued Invoice Gross KRW (VAT incl)":str(gross),
            "Issued Net Revenue KRW (VAT excl)":str(amount),
            "Issued Net Revenue kUSD @1500":str(round(amount/1500000,3)),
            "Issued Invoice Count":str(count),"Verified Pending KRW (VAT basis unverified)":"18429400",
            "Forecast KRW (estimate, separate)":"43767645",
            "Verified At KST":"2026-11-06 11:58:15 KST",
            "Evidence State":"INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"})
        life.append({"Month":month,"Actual Invoice KRW":"₩"+format(gross,","),
                     "Invoice Count":str(count),
                     "Pending Verified KRW":"₩18,429,400",
                     "Forecast KRW":"₩43,767,645"})
        for role,tab,basis,parity,value in [
                ("CANONICAL_ACTUAL_GROSS","BI Revenue Lifecycle Monthly","VAT_INCLUDED",
                 "MATCHED_TO_NET_AUDIT",gross),
                ("CANONICAL_ISSUED_NET","BI Revenue Net VAT Monthly","VAT_EXCLUDED",
                 "MATCHED_TO_INVOICE_SOURCE",amount)]:
            auth.append({"Month":month,"Source Tab":tab,"Source Role":role,
                         "Issued Invoice Count":str(count),"Amount KRW":str(value),
                         "Tax Basis":basis,"Source Parity":parity,
                         "Authoritative For KPI":"YES",
                         "Verified KST":"2026-11-08 08:55:12 KST"})
    # Future forecasting does not establish an issued invoice.
    net.append({
        "Month":"2026-12","Issued Invoice Gross KRW (VAT incl)":"0",
        "Issued Net Revenue KRW (VAT excl)":"0","Issued Invoice Count":"0",
        "Verified Pending KRW (VAT basis unverified)":"0",
        "Forecast KRW (estimate, separate)":"36821310",
        "Verified At KST":"2026-11-06 11:58:15 KST",
        "Evidence State":"INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"})
    life.append({"Month":"2026-12","Actual Invoice KRW":"₩0","Invoice Count":"0"})
    return {"BI Revenue Net VAT Monthly":net,"BI Revenue Lifecycle Monthly":life,
            "Revenue Source Authority":auth}


class MonthlyRevenueEvidenceTests(unittest.TestCase):
    def test_authoritative_oct_nov_count_net_gross_and_no_forecast(self):
        rows=evidence_rows(source())
        self.assertEqual([r["Month"] for r in rows],["2026-11","2026-10"])
        nov,oct=rows
        self.assertEqual((nov["Invoice Count"],nov["Tax Invoice KRW Incl VAT"],
                          nov["Net Revenue KRW Ex VAT"]),(4,38261300,34783000))
        self.assertEqual((oct["Invoice Count"],oct["Tax Invoice KRW Incl VAT"],
                          oct["Net Revenue KRW Ex VAT"]),(48,158541900,144129000))
        self.assertEqual(nov["Net Revenue M KRW"],34.783)
        self.assertEqual(oct["Net Revenue M KRW"],144.129)
        self.assertAlmostEqual(nov["Net Revenue K USD"],23.1887,places=4)
        self.assertEqual(oct["Net Revenue K USD"],96.086)
        self.assertTrue(all(x["Coverage Status"]=="QQ_ISSUED_VERIFIED_ERP_MANUAL_SCOPE_REVIEW"
                            for x in rows))
        self.assertTrue(all("manual ERP billing" in x["Evidence"]
                            for x in rows))
        self.assertNotIn("2026-12",[r["Month"] for r in rows])
        self.assertNotIn("43767645",str(rows))
        self.assertTrue(all(r["CSS Source Invoice Count"] is None for r in rows))
        self.assertTrue(all("2026-11-06 11:58:15 KST" in r["Evidence"] for r in rows))

    def test_mismatched_authoritative_gross_is_rejected(self):
        data=source()
        data["BI Revenue Lifecycle Monthly"][1]["Actual Invoice KRW"]="₩38,261,301"
        with self.assertRaisesRegex(RevenueEvidenceError,"LIFECYCLE"):
            evidence_rows(data)

    def test_outdated_or_non_authoritative_legacy_not_accepted(self):
        data=source()
        data["Revenue Source Authority"][3]["Authoritative For KPI"]="NO"
        with self.assertRaisesRegex(RevenueEvidenceError,"AUTHORITY"):
            evidence_rows(data)

    def test_authority_amount_mismatch_rejected(self):
        data=source()
        data["Revenue Source Authority"][3]["Amount KRW"]="40000000"
        with self.assertRaisesRegex(RevenueEvidenceError,"AUTHORITY"):
            evidence_rows(data)

    def test_invoice_count_and_vat_parity_fail_closed(self):
        data=source()
        data["BI Revenue Net VAT Monthly"][1]["Issued Invoice Count"]="5"
        with self.assertRaisesRegex(RevenueEvidenceError,"LIFECYCLE"):
            evidence_rows(data)
        data=source()
        data["BI Revenue Net VAT Monthly"][1]["Issued Net Revenue KRW (VAT excl)"]="34000000"
        with self.assertRaisesRegex(RevenueEvidenceError,"VAT_PARITY"):
            evidence_rows(data)

    def test_duplicate_authoritative_month_rejected(self):
        data=source()
        data["BI Revenue Net VAT Monthly"].append(
            copy.deepcopy(data["BI Revenue Net VAT Monthly"][0]))
        with self.assertRaisesRegex(RevenueEvidenceError,"DUPLICATE_MONTH"):
            evidence_rows(data)

    def test_missing_source_not_filled_with_guessed_numbers(self):
        data=source()
        data.pop("Revenue Source Authority")
        with self.assertRaisesRegex(RevenueEvidenceError,"MANDATORY_SOURCE_MISSING"):
            evidence_rows(data)

    def test_forecast_only_snapshot_never_published_as_actual(self):
        data=source()
        data["BI Revenue Net VAT Monthly"]=data["BI Revenue Net VAT Monthly"][-1:]
        with self.assertRaisesRegex(RevenueEvidenceError,"NO_ISSUED_MONTHS"):
            evidence_rows(data)

if __name__=="__main__":
    unittest.main()
