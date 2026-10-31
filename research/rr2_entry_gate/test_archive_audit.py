"""Synthetic aggregate-only archive contracts; never embeds private SIP bars."""
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("rr2_archive_audit", Path(__file__).with_name("archive_audit.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def synthetic():
    policies = {
        "BASE_STOP125_TP300": (1.25, 3.0),
        "MODERATE_STOP100_TP250": (1.0, 2.5),
        "TIGHT_STOP075_TP225": (0.75, 2.25),
    }
    d = {
        "schema": "kalman-regime-netRR2-geometry-feasibility-v1",
        "status": "RESEARCH_ONLY_NO_TRADE_PROMOTION",
        "decision": "HOLD",
        "no_live_or_broker_change": True,
        "2025_2026_not_fresh_out_of_sample": True,
        "hard_minimum_net_RR": 2.0,
        "roundtrip_cost_fraction": .003,
        "research_policies": {k: {"stop_atr_mult": v[0], "target_atr_mult": v[1]} for k, v in policies.items()},
        "data_qa": {"complete_symbol_sessions": 3555, "partial_or_missing_symbol_sessions": 0},
        "by_symbol": {},
    }
    for symbol in ("COIN", "IWM"):
        d["by_symbol"][symbol] = {}
        for year in ("2025", "2026"):
            d["by_symbol"][symbol][year] = {}
            for model in ("P_unweighted", "V_unweighted"):
                entries = {}
                n = (80 if year == "2025" else 46) if symbol == "COIN" else (72 if year == "2025" else 57)
                admitted = 0 if symbol == "COIN" else (23 if year == "2025" else 27)
                for arm in policies:
                    opportunity = {
                        "original_signal_count": n,
                        "passed_pre_entry_geometry": admitted,
                        "rejection_causes": {"PASS": admitted, "STOP_TOO_WIDE": n - admitted},
                        "causes_are_hierarchical_first_failure": True,
                    }
                    metric = {
                        "trades": admitted, "signal_count": n,
                        "realized_expectancy_R": .03 if admitted else None,
                        "exit_reason_counts": {"TIME_CLOSE": admitted},
                        "average_net_trade_pct": .1 if admitted else None,
                        "cum_return_pct": 1. if admitted else 0.,
                        "mdd_eod_pct": -1. if admitted else 0.,
                    }
                    entries[arm] = {"opportunity_feasibility": opportunity,
                                    "by_horizon": {h: {"MIN_NET_RR_GATE": dict(metric)} for h in ("1", "2", "4")}}
                d["by_symbol"][symbol][year][model] = entries
    qa = {"source": {"feed": "sip", "timeframe": "15Min"}, "status": "SOURCE_COVERAGE_GO_MODEL_HOLD"}
    return d, qa


def write_zip(path, report, qa):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("regime_rr2_feasibility.json", json.dumps(report))
        z.writestr("source_qa.json", json.dumps(qa))


class ArchiveContracts(unittest.TestCase):
    def test_aggregate_audit_hold(self):
        d, qa = synthetic()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "evidence.zip"
            write_zip(p, d, qa)
            a = audit.audit_archive(p)
            self.assertEqual(a["status"], "VERIFIED_RESEARCH_LIVE_HOLD")
            self.assertEqual(len(a["rows"]), 72)
            self.assertFalse(a["independent_reject_causes_available"])

    def test_promoted_or_incomplete_data_blocked(self):
        d, qa = synthetic()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "evidence.zip"
            d["decision"] = "GO"
            write_zip(p, d, qa)
            with self.assertRaisesRegex(ValueError, "UNSAFE_RESEARCH_GATE"):
                audit.audit_archive(p)
            d["decision"] = "HOLD"
            d["data_qa"]["partial_or_missing_symbol_sessions"] = 1
            write_zip(p, d, qa)
            with self.assertRaisesRegex(ValueError, "INCOMPLETE_SOURCE"):
                audit.audit_archive(p)

    def test_candidate_or_exit_mismatch_blocked(self):
        d, qa = synthetic()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "evidence.zip"
            item = d["by_symbol"]["IWM"]["2025"]["V_unweighted"]["BASE_STOP125_TP300"]
            item["by_horizon"]["1"]["MIN_NET_RR_GATE"]["exit_reason_counts"]["TIME_CLOSE"] = 22
            write_zip(p, d, qa)
            with self.assertRaisesRegex(ValueError, "EXIT_OR_COHORT_MISMATCH"):
                audit.audit_archive(p)


if __name__ == "__main__":
    unittest.main()
