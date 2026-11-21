"""No-network tests: official symbol directory is a dated snapshot, never history."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from zipfile import ZipFile

from daily20 import load_spec
import official_listing_directory as od

STAMP = "2026-11-21T15:30:00+00:00"
FOOTER = "File Creation Time: 1120202617:30"
SPEC = load_spec()
EQUITIES = [s for s in SPEC["core"] + SPEC["context"] if s != "^VIX"]


def fixture(*, changed=False, stale=False, removed=None, duplicate=None):
    assert len(EQUITIES) == 25
    nrows, orows = [], []
    for i, symbol in enumerate(EQUITIES):
        if symbol == removed:
            continue
        if i % 3 == 0:
            orows.append((symbol, "P" if i % 2 == 0 else "N"))
        else:
            nrows.append(symbol)
    nrows += [f"QA{i:05d}" for i in range(1200)]
    orows += [(f"QB{i:05d}", "N") for i in range(1200)]
    if duplicate:
        nrows.append(duplicate)
    header1 = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
    header2 = "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"
    lines1 = [header1] + [f"{s}|Test {s}|Q|N|N|100|N|N" for s in nrows]
    lines2 = [header2] + [
        f"{s}|Test {s}{' Changed' if changed and s == 'SPY' else ''}|{e}|{s}|Y|100|N|{s}"
        for s, e in orows
    ]
    footer = "File Creation Time: 0810202615:41" if stale else FOOTER
    return {
        "nasdaqlisted": ("\n".join(lines1 + [footer + "|||||||"]) + "\n").encode(),
        "otherlisted": ("\n".join(lines2 + [footer + "|||||||"]) + "\n").encode(),
    }


def as_fetcher(d):
    return lambda url: d[url.rsplit("/", 1)[-1].removesuffix(".txt")]


class OfficialDirectoryTests(TestCase):
    def test_footers_and_exchange_codes_are_in_source(self):
        blobs = fixture()
        n, nr = od.parse_directory(blobs["nasdaqlisted"], "nasdaqlisted")
        o, other = od.parse_directory(blobs["otherlisted"], "otherlisted")
        self.assertEqual(n["file_creation_date"], "2026-11-20")
        self.assertEqual(o["file_creation_date"], "2026-11-20")
        self.assertEqual(nr["QQQ"]["exchange"], "Q")
        self.assertEqual(other["SPY"]["exchange"], "P")
        self.assertEqual(n["sha256"], od.sha256(blobs["nasdaqlisted"]).hexdigest())
        self.assertEqual(o["sha256"], od.sha256(blobs["otherlisted"]).hexdigest())

    def test_25_current_snapshots_not_retroactively_asof_certified(self):
        result = od.one_snapshot(SPEC, fixture(), fetched_at=STAMP)
        self.assertEqual(result["required"], 25)
        self.assertEqual(result["snapshot_listed_count"], 25)
        self.assertEqual(result["research_listing_observed"], 25)
        self.assertEqual(result["finality_verified"], 0)
        self.assertFalse(result["source_snapshot_is_historical_asof_evidence"])
        self.assertTrue(all(not r["historical_session_listing_certified"]
                            for r in result["rows"]))
        self.assertEqual(result["status"], "OFFICIAL_DIRECTORY_SNAPSHOT_RESEARCH_HOLD")

    def test_missing_ticker_not_projected_from_current_alpaca_master(self):
        d = fixture(removed="SPY")
        r = od.one_snapshot(SPEC, d, fetched_at=STAMP)
        row = next(x for x in r["rows"] if x["symbol"] == "SPY")
        self.assertEqual(row["status"], "OFFICIAL_DIRECTORY_SYMBOL_MISSING_HOLD")
        self.assertEqual(row["venue"], None)
        self.assertEqual(r["research_listing_observed"], 24)

    def test_alpaca_disagreement_is_hold(self):
        venue = {
            "tested_assets": 25, "finality_verified": 0,
            "rows": [{"symbol": s, "selected_primary_venue_code": "N"} for s in EQUITIES]
        }
        r = od.one_snapshot(SPEC, fixture(), fetched_at=STAMP, current_venue=venue)
        qqq = next(x for x in r["rows"] if x["symbol"] == "QQQ")
        self.assertEqual(qqq["status"], "OFFICIAL_DIRECTORY_VS_ALPACA_VENUE_CONFLICT_HOLD")
        self.assertGreater(r["venue_disagreements"], 0)
        self.assertEqual(r["finality_verified"], 0)

    def test_stale_official_directory_is_research_hold(self):
        r = od.one_snapshot(SPEC, fixture(stale=True), fetched_at=STAMP)
        self.assertTrue(r["source_stale"])
        self.assertEqual(r["research_listing_observed"], 0)
        self.assertEqual(r["snapshot_listed_count"], 25)

    def test_missing_file_creation_footer_or_duplicate_ticker_rejected(self):
        d = fixture()
        bad = d["nasdaqlisted"].replace(FOOTER.encode(), b"No Creation Timestamp")
        with self.assertRaisesRegex(ValueError, "MISSING_CREATION"):
            od.parse_directory(bad, "nasdaqlisted")
        bad = fixture(duplicate="QQQ")
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            od.parse_directory(bad["nasdaqlisted"], "nasdaqlisted")

    def test_hash_chained_journal_preserves_same_source_snapshot(self):
        r = od.one_snapshot(SPEC, fixture(), fetched_at=STAMP)
        first, report = od.save_journal([], r, prior_status="FIRST_OFFICIAL_DIRECTORY_CAPTURE")
        self.assertEqual(len(first), 1)
        self.assertEqual(report["status"], "NEW_OFFICIAL_SNAPSHOT_APPEND")
        second, again = od.save_journal(first, r, prior_status="CONTINUED_FROM_PRIOR_DRIVE_RESULTS")
        self.assertEqual(len(second), 1)
        self.assertEqual(again["status"], "IDENTICAL_SOURCE_SNAPSHOT_ALREADY_SEALED")
        self.assertEqual(od.verify_chain(second), first[0]["hash"])

    def test_changed_vendor_bytes_same_creation_date_are_recorded_not_overwritten(self):
        a = od.one_snapshot(SPEC, fixture(), fetched_at=STAMP)
        b = od.one_snapshot(SPEC, fixture(changed=True), fetched_at=STAMP)
        journal, _ = od.save_journal([], a, prior_status="START")
        newer, result = od.save_journal(journal, b, prior_status="RESTORED")
        self.assertEqual(result["status"], "SAME_FILE_CREATION_DATES_CHANGED_BYTES_HOLD")
        self.assertEqual(len(newer), 2)
        self.assertEqual(newer[0], journal[0])
        self.assertEqual(od.verify_chain(newer), newer[-1]["hash"])

    def test_tampering_journal_rejected(self):
        r = od.one_snapshot(SPEC, fixture(), fetched_at=STAMP)
        journal, _ = od.save_journal([], r, prior_status="FIRST")
        corrupted = deepcopy(journal)
        corrupted[0]["symbols"]["QQQ"] = "N"
        with self.assertRaisesRegex(ValueError, "CHAIN_INVALID"):
            od.verify_chain(corrupted)

    def test_prior_drive_zip_reopens_hash_chain_without_external_io(self):
        r = od.one_snapshot(SPEC, fixture(), fetched_at=STAMP)
        first, _ = od.save_journal([], r, prior_status="FIRST")
        with TemporaryDirectory() as folder:
            zip_path = Path(folder) / "older_results.zip"
            with ZipFile(zip_path, "w") as z:
                z.writestr(od.JOURNAL_MEMBER,
                           "".join(json.dumps(e) + "\n" for e in first))
            loaded, state = od.previous_chain(zip_path)
            self.assertEqual(state, "CONTINUED_FROM_PRIOR_DRIVE_RESULTS")
            self.assertEqual(loaded, first)

    def test_preview_no_journal_seal_and_source_failure_holds(self):
        with TemporaryDirectory() as folder:
            result = od.run(SPEC, folder, fetcher=as_fetcher(fixture()),
                            stamp=STAMP, preview=True)
            self.assertEqual(result["journal"]["status"], "PR_PREVIEW_NO_SEAL")
            self.assertFalse((Path(folder) / "snapshot_journal.jsonl").exists())
            self.assertTrue((Path(folder) / "raw" / "nasdaqlisted.txt").exists())
            self.assertFalse(result["source_snapshot_is_historical_asof_evidence"])
            self.assertEqual(result["finality_verified"], 0)
        with TemporaryDirectory() as folder:
            result = od.run(SPEC, folder,
                            fetcher=lambda _: (_ for _ in ()).throw(ValueError("EXAMPLE")),
                            stamp=STAMP, preview=True)
            self.assertEqual(result["status"], "OFFICIAL_DIRECTORY_SOURCE_UNAVAILABLE_HOLD")
            self.assertEqual(result["finality_verified"], 0)


if __name__ == "__main__":
    main()
