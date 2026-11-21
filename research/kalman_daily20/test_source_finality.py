"""Prospective Daily20 external price finality is a fail-closed, typed contract."""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
from source_finality import (
    AFTER_HOURS, REGULAR, UNKNOWN, checked_reference, classify_quote, run, VERSION
)
from daily20 import load_spec, market_file


class Daily20SourceFinalityTests(unittest.TestCase):
    def reference(self, *, typ=REGULAR, adjustment="RAW", price=10., symbol="SPY"):
        return {
            "symbol":symbol,"quote_type":typ,"price":price,"adjustment":adjustment,
            "provider":"test-public-source","feed":"published-site",
            "observed_at_utc":"2026-11-20T21:00:00Z",
            "fetched_at_utc":"2026-11-21T03:00:00Z",
            "self_declared_independent":True,  # a claim alone is not trusted
        }

    def test_reference_never_auto_certifies(self):
        self.assertEqual(
            classify_quote(10.,False,self.reference()),
            "PUBLISHED_REGULAR_REFERENCE_MATCH_NOT_CERTIFIED")
        self.assertEqual(
            classify_quote(11.,False,self.reference()),
            "PUBLISHED_REGULAR_REFERENCE_CONFLICT_HOLD")

    def test_adjustment_factor_cannot_be_assumed(self):
        self.assertEqual(
            classify_quote(10.,True,self.reference()),
            "ADJUSTMENT_CONVENTION_NOT_COMPARABLE")
        self.assertEqual(
            classify_quote(10.,False,self.reference(adjustment="YAHOO_AUTO_ADJUSTED")),
            "ADJUSTMENT_CONVENTION_NOT_COMPARABLE")

    def test_afterhours_never_regular_close(self):
        ref=self.reference(typ=AFTER_HOURS,price=697.49)
        self.assertEqual(classify_quote(697.49,False,ref),
                         "AFTER_HOURS_QUOTE_MATCH_RESEARCH_HOLD")
        self.assertEqual(classify_quote(689.81,False,ref),
                         "AFTER_HOURS_QUOTE_DIFFERENT_RESEARCH_HOLD")
        self.assertEqual(classify_quote(10.,False,None),
                         "NO_INDEPENDENT_REGULAR_CLOSE_REFERENCE")

    def test_quote_type_rejected_if_wrong_or_unknown_with_price(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"r.json"
            doc={"schema":"daily20-quote-reference-v1","session":"2026-11-20",
                 "research_only":True,"quotes":[self.reference(typ="LATEST")]}
            p.write_text(json.dumps(doc))
            with self.assertRaisesRegex(RuntimeError,"UNDEFINED_QUOTE_TYPE"):
                checked_reference(p,"2026-11-20",{"SPY"})
            doc["quotes"]=[self.reference(typ=UNKNOWN)]
            p.write_text(json.dumps(doc))
            with self.assertRaisesRegex(RuntimeError,"UNKNOWN_QUOTE_WITH_PRICE"):
                checked_reference(p,"2026-11-20",{"SPY"})

    def test_wrong_session_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"r.json"
            obj={"schema":"daily20-quote-reference-v1","session":"2026-11-19",
                 "research_only":True,"quotes":[self.reference()]}
            p.write_text(json.dumps(obj))
            with self.assertRaisesRegex(RuntimeError,"SESSION_MISMATCH"):
                checked_reference(p,"2026-11-20",{"SPY"})

    def test_missing_timestamp_and_provider_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"r.json"
            quote=self.reference()
            quote.pop("provider")
            p.write_text(json.dumps({
                "schema":"daily20-quote-reference-v1","session":"2026-11-20",
                "research_only":True,"quotes":[quote],
            }))
            with self.assertRaisesRegex(RuntimeError,"PROVENANCE_INCOMPLETE"):
                checked_reference(p,"2026-11-20",{"SPY"})

    def test_typed_missing_26_asset_run_produces_hold_not_fake_go(self):
        spec=load_spec()
        with TemporaryDirectory() as d:
            root=Path(d)/"market"
            date=pd.Timestamp("2026-11-20T00:00:00Z")
            for s in spec["core"]+spec["context"]:
                p=market_file(root,s)
                p.parent.mkdir(parents=True,exist_ok=True)
                pd.DataFrame([{
                    "timestamp":date,"open":100.,"high":102.,"low":99.,
                    "close":101.,"volume":2000.,
                    "is_adjusted": s!="^VIX"
                }]).to_parquet(p,index=False)
            qc=Path(d)/"qc.json"
            qc.write_text(json.dumps({
                "expected_session":"2026-11-20","status":"READY",
                "required":26,"ready":26
            }))
            report=run(spec,qc,root,Path(d)/"report.json",
                fetched_at="2026-11-21T07:00:00+00:00")
            self.assertEqual(report["version"],VERSION)
            self.assertEqual(report["status"],"SOURCE_FINALITY_HOLD")
            self.assertTrue(report["research_hold"])
            self.assertTrue(report["new_signals_must_be_provisional"])
            self.assertEqual((report["verified"],report["required"],report["examined"]),(0,26,26))
            self.assertTrue(all(not row["finality_verified"] for row in report["symbols"]))
            self.assertEqual(sum(row["group"]=="CORE_20" for row in report["symbols"]),20)
            self.assertEqual(sum(row["group"]=="CONTEXT_6" for row in report["symbols"]),6)
            # VIX is unadjusted, while 25 stocks/ETFs use Yahoo auto-adjusted bars.
            # Their bytes and therefore SHA256 differ even with identical OHLCV.
            self.assertEqual(len({row["source_parquet_sha256"] for row in report["symbols"]}),2)
            self.assertEqual(sum(row["yahoo_is_adjusted"] for row in report["symbols"]),25)
            self.assertFalse(report["strategy_promoted"])


if __name__=="__main__":
    unittest.main()
