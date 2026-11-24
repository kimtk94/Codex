"""Historical point-in-time listing research boundary (no trading/price promotion)."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import listing_asof as la
from daily20 import load_spec


class ListingAsOfTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_spec()
        self.src = json.loads(Path(la.DEFAULT_SOURCES).read_text())

    def test_issuer_and_exchange_notice_bound_pltr_nov_transfer(self):
        index,docs,names = la.validate(self.src,self.spec)
        self.assertEqual(len(names),25)
        prev=la.lookup(index,docs,"PLTR","2024-11-25")
        next=la.lookup(index,docs,"PLTR","2024-11-26")
        self.assertEqual((prev["venue"],prev["sip_code"]),("NYSE","N"))
        self.assertEqual((next["venue"],next["sip_code"]),("NASDAQ","Q"))
        self.assertFalse(prev["asof_certified"])
        self.assertFalse(next["asof_certified"])
        self.assertFalse(next["page_bytes_independently_archived"])

    def test_historic_coverage_has_stated_expiration(self):
        index,docs,_=la.validate(self.src,self.spec)
        self.assertEqual(la.lookup(index,docs,"PLTR","2024-12-31")["sip_code"],"Q")
        self.assertEqual(la.lookup(index,docs,"PLTR","2025-01-01")["status"],
                         "NO_DATED_LISTING_EVIDENCE_HOLD")
        self.assertEqual(la.lookup(index,docs,"PLTR","2020-09-29")["status"],
                         "NO_DATED_LISTING_EVIDENCE_HOLD")
        self.assertEqual(la.lookup(index,docs,"QQQ","2024-11-26")["status"],
                         "NO_DATED_LISTING_EVIDENCE_HOLD")

    def test_asof_2026_not_retroactively_promoted_from_current_master(self):
        result=la.audit(self.spec,self.src,"2026-11-20")
        self.assertEqual(result["required"],25)
        self.assertEqual(result["documented_historical_symbols"],1)
        self.assertEqual(result["documented_historical_intervals"],2)
        self.assertEqual(result["asof_research_interval_covered"],0)
        self.assertEqual(result["historical_listing_asof_certified"],0)
        self.assertEqual(result["finality_verified"],0)
        self.assertTrue(result["research_only"])
        self.assertFalse(result["strategy_promoted"])
        self.assertEqual(len(result["rows"]),25)

    def test_previous_current_venue_report_only_added_as_uncertified_context(self):
        rows=[{"symbol":x,"asset_exchange":"NASDAQ","selected_primary_venue_code":"Q"}
              for x in self.spec["core"]+self.spec["context"] if x!="^VIX"]
        result=la.audit(self.spec,self.src,"2026-11-20",venue_reference={
            "session":"2026-11-20","tested_assets":25,"finality_verified":0,
            "rows":rows,
        })
        pltr=next(x for x in result["rows"] if x["symbol"]=="PLTR")
        self.assertEqual(pltr["provider_current_master_exchange"],"NASDAQ")
        self.assertFalse(pltr["provider_current_master_is_historical_evidence"])
        self.assertEqual(pltr["status"],"NO_DATED_LISTING_EVIDENCE_HOLD")
        self.assertFalse(pltr["current_raw_m_price_certified"])

    def test_overlap_venue_conflict_rejected(self):
        bad=deepcopy(self.src)
        bad["intervals"][1]["from"]="2024-11-25"
        with self.assertRaisesRegex(ValueError,"OVERLAPPING_VENUE"):
            la.validate(bad,self.spec)

    def test_historic_future_extrapolation_rejected(self):
        bad=deepcopy(self.src)
        bad["intervals"][1]["to_exclusive"]="2026-01-01"
        with self.assertRaisesRegex(ValueError,"BEYOND_SOURCE_PERIOD"):
            la.validate(bad,self.spec)

    def test_unsafe_venue_alias_or_code_rejected(self):
        bad=deepcopy(self.src)
        bad["intervals"][0]["official_sip_code"]="Q"
        with self.assertRaisesRegex(ValueError,"SIP_CODE_MISMATCH"):
            la.validate(bad,self.spec)

    def test_missing_source_or_unverified_digest_forbidden(self):
        bad=deepcopy(self.src)
        bad["intervals"][0]["source_ids"]=["FAKE"]
        with self.assertRaisesRegex(ValueError,"MISSING_OFFICIAL_DOCUMENT"):
            la.validate(bad,self.spec)
        bad=deepcopy(self.src)
        bad["sources"][0]["retrieved_page_sha256"]="a"*64
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_PAGE_DIGEST"):
            la.validate(bad,self.spec)

    def test_nonofficial_domain_rejected(self):
        bad=deepcopy(self.src)
        bad["sources"][0]["url"]="https://example.com/pltr"
        with self.assertRaisesRegex(ValueError,"NOT_OFFICIAL_ALLOWLIST"):
            la.validate(bad,self.spec)

    def test_output_stays_research_only_and_no_sensitive_vendor_data(self):
        with TemporaryDirectory() as d:
            qc=Path(d)/"qc.json"
            qc.write_text(json.dumps({"expected_session":"2026-11-20","ready":26,"status":"READY"}))
            out=Path(d)/"report.json"
            report=la.audit(self.spec,self.src,json.loads(qc.read_text())["expected_session"])
            la.write_json(out,report)
            copy=json.loads(out.read_text())
            self.assertEqual(copy["pltr_transfer_regression"][0]["sip_code"],"N")
            self.assertEqual(copy["pltr_transfer_regression"][1]["sip_code"],"Q")
            self.assertEqual(copy["status"],"HISTORICAL_LISTING_ASOF_RESEARCH_HOLD")
            self.assertEqual(copy["finality_verified"],0)


if __name__=="__main__":
    unittest.main()
