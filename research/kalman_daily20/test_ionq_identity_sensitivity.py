"""Contract: pre-IonQ ticker rows must be excluded without retroactive signal edits."""
from __future__ import annotations

import unittest
import pandas as pd

from ionq_identity_sensitivity import CUTOFF, cutoff_frame, ARCHIVES_SHA256, RUNS


class IonqIdentityContracts(unittest.TestCase):
    def test_listing_date_is_fixed(self):
        self.assertEqual(str(CUTOFF.date()), "2021-10-01")
        self.assertEqual(len(RUNS), 2)
        self.assertTrue(all(len(v) == 64 for v in ARCHIVES_SHA256.values()))

    def test_spac_predecessor_history_is_removed(self):
        original = pd.DataFrame({
            "timestamp":pd.to_datetime([
                "2021-09-29","2021-09-30","2021-10-01","2021-10-04"],utc=True),
            "close":[10.1,10.2,9.0,8.8],
            "symbol":["IONQ"]*4,
        })
        result = cutoff_frame(original)
        self.assertEqual(len(result), 2)
        self.assertEqual(str(result.iloc[0]["timestamp"].date()),"2021-10-01")
        self.assertEqual(len(original),4)
        self.assertEqual(result["close"].tolist(),[9.0,8.8])

    def test_no_hindsight_listing_date(self):
        pre = pd.DataFrame({"timestamp":pd.to_datetime([
            "2021-09-28","2021-09-30"],utc=True)})
        with self.assertRaisesRegex(RuntimeError,"IONQ_EXPECTED_FIRST_LISTED_DATE_NOT_FOUND"):
            # At least one post-date sample, but missing the actual listing date.
            cutoff_frame(pd.concat([pre,pd.DataFrame({
                "timestamp":pd.to_datetime(["2021-10-04"],utc=True),
            })],ignore_index=True))

    def test_no_prelisting_rows_or_forged_listing(self):
        after = pd.DataFrame({"timestamp":pd.to_datetime([
            "2021-10-01","2021-10-04"],utc=True)})
        with self.assertRaisesRegex(RuntimeError,"IONQ_CUTOFF_NO_PREDECESSOR_ROWS"):
            cutoff_frame(after)

    def test_invalid_time_format_rejected(self):
        values = pd.DataFrame({"timestamp":["wrong","2021-10-01"]})
        with self.assertRaises(Exception):
            cutoff_frame(values)


if __name__=="__main__":
    unittest.main()
