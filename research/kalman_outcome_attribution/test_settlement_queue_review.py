import csv
import io
import json
import unittest

import exchange_calendars as xc
import pandas as pd

from settlement_queue_review import (
    COLS, CLEAN, PENDING, REVISED, compare_queue, pair_manifest,
    price_revision_issues, queue_row,
)
from prospective_gate_readiness import sha, sessions


class SettlementReconciliationContracts(unittest.TestCase):
    def setUp(self):
        self.cal=xc.get_calendar("XNYS",start="2026-01-01",end="2028-02-01")
        self.day="2026-11-25"
        self.key=(self.day,"SPY","BULL_LOGISTIC")
        self.signal={"horizon_us_sessions":4,"recorded_at_utc":"2026-11-25T22:00:00Z",
                     "candidate":True,"hash":"a"*64,"probability":.7}
        self.window=sessions(self.cal,self.day)
        idx=pd.DatetimeIndex([pd.Timestamp(s.date()) for s in self.window])
        self.bars=pd.DataFrame({"open":[100.,100.,101.,102.,103.],
                                "close":[100.,101.,102.,103.,104.],
                                "high":[101.,102.,103.,104.,105.],
                                "low":[99.,98.,100.,101.,102.]},index=idx)
        self.event={"hash":"b"*64,"entry_date":"2026-11-27","exit_date":"2026-12-02",
                    "recorded_at_utc":"2026-12-02T22:00:00Z","entry_open":100.,
                    "exit_close":104.,"gross_return":.04,
                    "next_open_gap_return":0.,"worst_four_session_low_vs_entry":-.02,
                    "net_return_by_cost_bp":{"20":.038,"40":.036,"80":.032},
                    "model_positive_probability_frozen":.7}

    def test_pair_rejects_different_capture(self):
        a={"source_actions_run_id":"1","payload_hashes_sha256":{"x":"a"}}
        b={"source_actions_run_id":"1","payload_hashes_sha256":{"y":"b"}}
        pair_manifest(a,b)
        with self.assertRaisesRegex(ValueError,"MARKET_RESULTS_CAPTURE_MISMATCH"):
            pair_manifest(a,dict(b,source_actions_run_id="2"))

    def test_pending_does_not_read_prices_and_overdue_fails(self):
        def no_prices(_):
            raise AssertionError("must not read pending prices")
        row=queue_row(self.key,self.signal,None,"2026-11-30",self.cal,no_prices)
        self.assertEqual(row["state"],PENDING)
        self.assertEqual(row["entry_date"],"2026-11-27")
        self.assertEqual(row["exit_date"],"2026-12-02")
        self.assertIsNone(row["cost_20bp_net_return"])
        with self.assertRaisesRegex(ValueError,"MATURED_SIGNAL_WITHOUT_SETTLEMENT"):
            queue_row(self.key,self.signal,None,"2026-12-02",self.cal,no_prices)

    def test_original_vs_revised_vendor_marks_preserves_settlement(self):
        self.assertEqual(price_revision_issues(self.event,self.bars,self.window),[])
        a=queue_row(self.key,self.signal,self.event,"2026-12-02",self.cal,lambda _:self.bars)
        self.assertEqual(a["state"],CLEAN)
        changed=self.bars.copy()
        changed.loc[changed.index[-1],"close"]=103.5
        b=queue_row(self.key,self.signal,self.event,"2026-12-02",self.cal,lambda _:changed)
        self.assertEqual(b["state"],REVISED)
        self.assertEqual(b["price_revision_issues"],["exit_close","gross_return"])
        self.assertEqual(a["cost_20bp_net_return"],b["cost_20bp_net_return"])
        self.assertEqual(a["original_settlement_hash"],b["original_settlement_hash"])

    def test_missing_window_and_invalid_ohlc_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"CURRENT_MARKET_WINDOW_INCOMPLETE"):
            price_revision_issues(self.event,self.bars.iloc[:-1],self.window)
        bad=self.bars.copy()
        bad.iloc[1,bad.columns.get_loc("low")]=110.
        with self.assertRaisesRegex(ValueError,"CURRENT_MARKET_WINDOW_INVALID"):
            price_revision_issues(self.event,bad,self.window)

    def test_recomputed_csv_json_and_counts_must_all_agree(self):
        row=queue_row(self.key,self.signal,None,"2026-11-30",self.cal,lambda _:None)
        buf=io.StringIO(newline="")
        writer=csv.DictWriter(buf,fieldnames=COLS,lineterminator="\n")
        writer.writeheader()
        writer.writerow({c:json.dumps(row[c]) if c=="price_revision_issues" else
                         "" if row[c] is None else row[c] for c in COLS})
        blob=buf.getvalue().encode()
        r={"observations":[row],"settlement_queue_csv_sha256":sha(blob),
           "signal_count":1,"bull_signals":1,"bear_signals":0,"settled_events":0,
           "pending_unmatured":1,"settled_arithmetic_verified":0,
           "settled_vendor_price_revisions":0,"candidate_settlements":0,
           "first_unsettled_exit_date":"2026-12-02"}
        self.assertEqual(compare_queue([row],r,blob)["pending_unmatured"],1)
        with self.assertRaisesRegex(ValueError,"PUBLISHED_QUEUE_COUNTS_MISMATCH"):
            compare_queue([row],dict(r,settled_events=1),blob)
        bad=blob.replace(b"2026-12-02",b"2026-12-01")
        with self.assertRaisesRegex(ValueError,"RECOMPUTED_CSV_QUEUE_MISMATCH"):
            compare_queue([row],dict(r,settlement_queue_csv_sha256=sha(bad)),bad)
        with self.assertRaisesRegex(ValueError,"RECOMPUTED_JSON_QUEUE_MISMATCH"):
            compare_queue([row],dict(r,observations=[dict(row,exit_date="2026-12-01")]),blob)


if __name__=="__main__":
    unittest.main()
