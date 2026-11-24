"""No-credentials 4-XNYS-settlement queue, arithmetic and immutable-event tests."""
from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch
import math
import unittest

import pandas as pd

from daily20 import load_spec
from forward_shadow import chain_append, new_observation, nyse_dates
from bear_forward import add_event, VERSION as BEAR_VERSION
from forward_settlement_integrity import audit, csv_blob

SPEC = load_spec()
FAMILIES = ("BULL_LOGISTIC", "BEAR_LOGISTIC", "BEAR_RULE")
SOURCE_DATE = "2026-11-23"
SETTLEMENT_DATE = "2026-11-30"
RECORD = "2026-12-01T02:40:00+00:00"


def signal_journals(session=SOURCE_DATE):
    bulls, bears = [], []
    for symbol in SPEC["core"]:
        b = chain_append(bulls, {
            "kind": "SIGNAL", "research_only": True,
            "signal_date": session, "symbol": symbol,
            "recorded_at_utc": "2026-11-24T02:40:00+00:00",
            "source_actions_run_id": "fixture-one",
            "probability": 0.65, "candidate": symbol == "SPY",
            "shadow_only": symbol in SPEC["high_risk_shadow_only"],
        })
        for family in ("BEAR_LOGISTIC", "BEAR_RULE"):
            add_event(bears, {
                "kind": "SIGNAL", "research_only": True, "signal_date": session,
                "symbol": symbol, "family": family,
                "recorded_at_utc": "2026-11-24T02:40:00+00:00",
                "source_actions_run_id": "fixture-one",
                "model_version": BEAR_VERSION,
                "baseline_signal_hash": b["hash"],
                "eligible": True, "candidate": family == "BEAR_LOGISTIC",
                "probability": 0.68 if family == "BEAR_LOGISTIC" else None,
                "feature_sha256": "a" * 64, "shadow_only":
                    symbol in SPEC["high_risk_shadow_only"],
            })
    return bulls, bears


def market_frame(session=SOURCE_DATE):
    _, dates = nyse_dates(session)
    indices = pd.DatetimeIndex([pd.Timestamp(s.date()) for s in dates])
    return pd.DataFrame({
        "open": [100., 100., 101., 102., 103.],
        "high": [104., 105., 106., 107., 113.],
        "low": [98., 97., 96., 95., 94.],
        "close": [99., 102., 103., 104., 110.],
        "volume": [1000.]*5,
    }, index=indices)


def complete_journals(session=SOURCE_DATE, asof=SETTLEMENT_DATE):
    bull, bear = signal_journals(session)
    frame = market_frame(session)
    with patch("forward_shadow.load_bars", return_value=frame):
        for e in list(bull):
            observation = new_observation(e, "/not-needed", asof, RECORD)
            if observation is not None:
                chain_append(bull, observation)
        for e in list(bear):
            observation = new_observation(e, "/not-needed", asof, RECORD)
            if observation is not None:
                add_event(bear, {**observation, "family": e["family"]})
    return bull, bear, frame


class FourSessionSettlementAudits(unittest.TestCase):
    def test_nyse_calendar_skips_thanksgiving_in_four_session_horizon(self):
        _, dates = nyse_dates("2026-11-23")
        self.assertEqual([str(d.date()) for d in dates], [
            "2026-11-23", "2026-11-24", "2026-11-25",
            "2026-11-27", "2026-11-30",
        ])
        _, old = nyse_dates("2026-11-20")
        self.assertEqual(str(old[4].date()), "2026-11-27")

    def test_zero_matured_on_first_frozen_day_is_not_positive_alpha(self):
        bull, bear = signal_journals()
        report = audit(SPEC, "/unused", SOURCE_DATE, bull, bear)
        self.assertEqual(report["signal_count"], 60)
        self.assertEqual(report["pending_unmatured"], 60)
        self.assertEqual(report["settled_events"], 0)
        self.assertEqual(report["first_unsettled_exit_date"], SETTLEMENT_DATE)
        self.assertFalse(report["actual_forward_outcomes_approved_for_attribution"])
        self.assertEqual(len(csv_blob(report["observations"]).splitlines()), 61)
        self.assertTrue(report["original_journals_unchanged"])

    def test_one_day_before_fourth_close_cannot_settle(self):
        bull, bear = signal_journals()
        report = audit(SPEC, "/unused", "2026-11-27", bull, bear)
        self.assertEqual(report["settled_events"], 0)
        self.assertEqual(report["pending_unmatured"], 60)

    def test_60_prospective_observations_mature_only_on_fourth_close(self):
        bull, bear, frame = complete_journals()
        with patch("forward_settlement_integrity.price_frame", return_value=frame):
            report = audit(SPEC, "/unused", SETTLEMENT_DATE, bull, bear)
        self.assertEqual(report["settled_events"], 60)
        self.assertEqual(report["pending_unmatured"], 0)
        self.assertEqual(report["settled_arithmetic_verified"], 60)
        self.assertEqual(report["settled_vendor_price_revisions"], 0)
        self.assertEqual(report["candidate_settlements"], 21)
        self.assertIsNone(report["first_unsettled_exit_date"])
        self.assertTrue(report["settlement_is_observation_not_executed_trade"])
        row = next(x for x in report["observations"]
                   if x["symbol"] == "SPY" and x["family"] == "BULL_LOGISTIC")
        self.assertEqual(row["entry_date"], "2026-11-24")
        self.assertEqual(row["exit_date"], SETTLEMENT_DATE)
        self.assertTrue(math.isclose(row["cost_20bp_net_return"], .098))

    def test_missing_matured_one_blocks_publishing(self):
        bull, bear, frame = complete_journals()
        bull = bull[:-1]  # drop one appended SETTLED: 19 Bull versus due 20
        with self.assertRaisesRegex(RuntimeError, "MATURED_4TH_SESSION_UNSETTLED"):
            audit(SPEC, "/unused", SETTLEMENT_DATE, bull, bear)

    def test_early_maturation_not_accepted_even_if_event_present(self):
        bull, bear, frame = complete_journals()
        with self.assertRaisesRegex(RuntimeError, "PREMATURE_4TH_SESSION_SETTLEMENT"):
            audit(SPEC, "/unused", "2026-11-27", bull, bear)

    def test_false_fourth_exit_date_is_rejected(self):
        bull, bear, frame = complete_journals()
        obs = next(x for x in bull if x["kind"] == "SETTLED")
        obs["exit_date"] = "2026-11-27"
        # In-memory tampering already breaks journal SHA, as it must.
        with self.assertRaisesRegex(RuntimeError, "JOURNAL_HASH_CHAIN"):
            audit(SPEC, "/unused", SETTLEMENT_DATE, bull, bear)

    def test_miscomputed_roundtrip_transaction_cost_is_rejected(self):
        bull, bear, frame = complete_journals()
        obs = next(x for x in bull if x["kind"] == "SETTLED")
        obs["net_return_by_cost_bp"]["20"] = .11
        from forward_shadow import event_hash
        # Re-sign all subsequent chain links to test the economic audit gate
        # rather than the basic tamper-evident hash guard.
        for i in range(len(bull)):
            bull[i]["prev_hash"] = bull[i-1]["hash"] if i else "0" * 64
            bull[i]["hash"] = event_hash(bull[i])
        with patch("forward_settlement_integrity.price_frame", return_value=frame):
            with self.assertRaisesRegex(RuntimeError, "ROUNDTRIP_COST_MISMATCH"):
                audit(SPEC, "/unused", SETTLEMENT_DATE, bull, bear)

    def test_vendor_revises_price_after_original_settlement_original_is_held(self):
        bull, bear, frame = complete_journals()
        revised = frame.copy()
        revised.loc[pd.Timestamp(SETTLEMENT_DATE), "close"] = 112.
        with patch("forward_settlement_integrity.price_frame",
                   return_value=revised):
            result = audit(SPEC, "/unused", SETTLEMENT_DATE, bull, bear)
        self.assertEqual(result["settled_events"], 60)
        self.assertEqual(result["settled_vendor_price_revisions"], 60)
        self.assertEqual(result["status"], "SETTLED_VENDOR_REVISION_RESEARCH_HOLD")
        self.assertEqual(result["observations"][0]["state"],
                         "SETTLED_VENDOR_HISTORY_REVISED_HOLD")
        self.assertFalse(result["actual_forward_outcomes_approved_for_attribution"])

    def test_wrong_bear_bull_anchor_fails_even_if_journal_sha_resigned(self):
        bull, bear = signal_journals()
        bear[0]["baseline_signal_hash"] = "b" * 64
        from forward_shadow import event_hash
        for i in range(len(bear)):
            bear[i]["prev_hash"] = bear[i-1]["hash"] if i else "0" * 64
            bear[i]["hash"] = event_hash(bear[i])
        with self.assertRaisesRegex(RuntimeError, "BEAR_BULL_ORIGINAL_ANCHOR_MISMATCH"):
            audit(SPEC, "/unused", SOURCE_DATE, bull, bear)

    def test_mismatched_journal_report_count_fail_closed(self):
        bull, bear = signal_journals()
        brep = {"last_completed_session": SOURCE_DATE,
                "signal_events": 20, "settled_events": 0,
                "research_only": True, "approved_live": False}
        rrep = {"last_completed_session": SOURCE_DATE,
                "signal_events": 41, "settled_events": 0,
                "research_only": True, "approved_live": False}
        with self.assertRaisesRegex(RuntimeError, "FORWARD_REPORT_VS_JOURNAL_MISMATCH"):
            audit(SPEC, "/unused", SOURCE_DATE, bull, bear,
                  report_bull=brep, report_bear=rrep)


if __name__ == "__main__":
    unittest.main()
