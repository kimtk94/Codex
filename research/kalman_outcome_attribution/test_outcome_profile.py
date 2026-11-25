import io
import json
import unittest
import zipfile

import numpy as np
import pandas as pd

from outcome_profile import (
    ASOF, FEATURES, RUN_ID, SOURCE_SHA, classify, join_signal_features,
    match_executions, profile, rank_auc, sha, summarize, verified_members,
)


def fixture():
    dates = pd.to_datetime(["2026-01-02","2026-01-05","2026-01-06","2026-01-07"])
    frame = pd.DataFrame({k:[1.,2.,3.,4.] for k in FEATURES},index=dates)
    frame["entry_date"] = pd.Series(dates,index=dates).shift(-1)
    frame["exit_date"] = pd.Series(dates,index=dates).shift(-2)
    frame["gross_return"] = [.012,-.058,np.nan,np.nan]
    frame["net_return"] = [.01,-.06,np.nan,np.nan]
    frame["future_secret"] = [999.,999.,999.,999.]
    events = pd.DataFrame({
        "family":["BULL_LOGISTIC"]*2, "symbol":["SPY"]*2,
        "signal_date":dates[:2].strftime("%Y-%m-%d"),
        "entry_date":dates[1:3].strftime("%Y-%m-%d"),
        "exit_date":dates[2:4].strftime("%Y-%m-%d"),
        "gross_return":[.012,-.058], "net_return":[.01,-.06],
        "probability":[.62,.65],
    })
    return events,frame


class OutcomeContracts(unittest.TestCase):
    def test_exact_signal_row_and_no_future_feature_leak(self):
        e,f=fixture()
        got=join_signal_features(e,{"SPY":f})
        self.assertEqual(got.ret1.tolist(),[1.,2.])
        self.assertTrue(set(FEATURES).issubset(got.columns))
        self.assertNotIn("future_secret",got)
        self.assertEqual(len(got),2)

    def test_missing_signal_duplicate_and_changed_labels_rejected(self):
        e,f=fixture()
        with self.assertRaisesRegex(ValueError,"MISSING_SIGNAL_FEATURE_ROW"):
            join_signal_features(e,{"SPY":f.iloc[1:]})
        with self.assertRaisesRegex(ValueError,"DUPLICATE_CANDIDATE_KEY"):
            join_signal_features(pd.concat([e,e]),{"SPY":f})
        changed=f.copy();changed.iloc[0,changed.columns.get_loc("gross_return")]=.2
        with self.assertRaisesRegex(ValueError,"ARCHIVED_LABEL_MISMATCH"):
            join_signal_features(e,{"SPY":changed})

    def test_changed_horizon_and_future_exit_rejected(self):
        e,f=fixture()
        changed=e.copy();changed.loc[0,"exit_date"]="2026-01-07"
        with self.assertRaisesRegex(ValueError,"ARCHIVED_HORIZON_MISMATCH"):
            join_signal_features(changed,{"SPY":f})
        changed.loc[0,"exit_date"]="2026-11-24"
        with self.assertRaisesRegex(ValueError,"INVALID_EVENT_SEQUENCE"):
            join_signal_features(changed,{"SPY":f})

    def test_outcome_boundaries_and_gross_loss_contribution(self):
        v=pd.Series([.02,0.,-.01,-.05,-.10])
        self.assertEqual(classify(v).tolist(),
                         ["WIN","BREAKEVEN","MILD_LOSS","SEVERE_LOSS","EXTREME_LOSS"])
        with self.assertRaisesRegex(ValueError,"NONFINITE_RETURN"):
            classify(pd.Series([np.nan]))
        g=pd.DataFrame({"r":v,"signal_date":pd.date_range("2026-01-01",periods=5),
                        "net_pnl":[20,0,-10,-50,-100]})
        s=summarize(g,"r")
        self.assertEqual(s["severe_loss_ge_5pct"],2)
        self.assertEqual(s["extreme_loss_ge_10pct"],1)
        self.assertAlmostEqual(s["severe_share_of_total_loss_pnl"],150/160)

    def test_rank_ties_missing_and_single_class(self):
        auc,pairs=rank_auc(pd.Series([1.,1.,np.nan,2.]),
                           pd.Series([True,False,True,True]))
        self.assertEqual(pairs,2)
        self.assertAlmostEqual(auc,.75)
        self.assertEqual(rank_auc(pd.Series([1.,2.]),pd.Series([True,True])),(None,0))

    def test_profile_missing_not_imputed(self):
        e,f=fixture();f.loc[f.index[0],"rsi14"]=np.nan
        g=join_signal_features(e,{"SPY":f})
        row=next(r for r in profile(g,"net_return")
                 if r["feature"]=="rsi14" and r["comparison"]=="WIN_VS_LOSS")
        self.assertEqual(row["positive_missing"],1)
        self.assertEqual(row["positive"]["n"],0)
        self.assertIsNone(row["rank_auc"])

    def test_filled_and_unfilled_preserve_distinct_returns(self):
        e,f=fixture();g=join_signal_features(e,{"SPY":f})
        ex=e.iloc[:1][["symbol","signal_date","entry_date","exit_date"]].copy()
        ex["realized_return"]=.009;ex["net_pnl"]=9.
        filled,unfilled=match_executions(g,ex)
        self.assertEqual(len(filled),1);self.assertEqual(len(unfilled),1)
        self.assertEqual(filled.realized_return.iloc[0],.009)
        self.assertEqual(filled.net_return.iloc[0],.01)
        ex["symbol"]="UNKNOWN"
        with self.assertRaisesRegex(ValueError,"EXECUTION_WITHOUT_CANDIDATE"):
            match_executions(g,ex)

    def test_archive_hash_and_member_contract(self):
        m={"format":"kalman-daily20-drive-v1","research_only":True,"production_writes":False,
           "source_sha":SOURCE_SHA,"source_actions_run_id":RUN_ID,
           "data_expected_last_closed_xnys":ASOF,"source_finality_status":"SOURCE_FINALITY_HOLD",
           "payload_hashes_sha256":{"test.csv":sha(b"original")}}
        def make(data):
            out=io.BytesIO()
            with zipfile.ZipFile(out,"w") as z:
                z.writestr("drive_manifest.json",json.dumps(m))
                z.writestr("test.csv",data)
            return out.getvalue()
        good=make(b"original")
        self.assertEqual(verified_members(good,expected_sha=sha(good),expected_count=1),
                         {"test.csv":b"original"})
        bad=make(b"changed")
        with self.assertRaisesRegex(ValueError,"ARCHIVE_SHA256_MISMATCH"):
            verified_members(bad,expected_sha=sha(good),expected_count=1)
        with self.assertRaisesRegex(ValueError,"ARCHIVE_MEMBER_HASH_MISMATCH"):
            verified_members(bad,expected_sha=sha(bad),expected_count=1)


if __name__=="__main__":
    unittest.main()
