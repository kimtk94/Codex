"""Fail-closed full raw source archival and Drive restore, without network."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from daily20 import load_spec
from official_listing_directory import (
    JOURNAL_MEMBER, one_snapshot, run, save_journal, verify_chain,
)
from official_directory_history import member_for, preserve
from test_official_listing_directory import fixture, as_fetcher, STAMP

SPEC=load_spec()
ROOT="research/official_directory/"


def from_first_snapshot(blobs):
    result=one_snapshot(SPEC,blobs,fetched_at=STAMP)
    return save_journal([],result,prior_status="FIRST_OFFICIAL_DIRECTORY_CAPTURE")[0]


def write_old_zip(zip_path, journal, blobs, *, full_history=False):
    with ZipFile(zip_path,"w") as z:
        z.writestr(JOURNAL_MEMBER, "".join(
            json.dumps(row,sort_keys=True)+"\n" for row in journal))
        for source,blob in blobs.items():
            z.writestr(ROOT+"raw/"+source+".txt",blob)
        if full_history:
            for event in journal:
                for source,digest in event["source_sha256"].items():
                    if sha256(blobs[source]).hexdigest()==digest:
                        z.writestr(member_for(source,digest),blobs[source])


def zipped_result(zip_path, output_dir):
    with ZipFile(zip_path,"w") as z:
        for p in output_dir.rglob("*"):
            if p.is_file():
                z.write(p,ROOT+p.relative_to(output_dir).as_posix())


class OfficialDirectoryHistoryTests(unittest.TestCase):
    def test_legacy_drive_zip_full_blob_bootstrap(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=fixture()
            chain=from_first_snapshot(data)
            old=root/"old.zip"
            write_old_zip(old,chain,data)
            report=run(SPEC,root/"next",fetcher=as_fetcher(data),
                       stamp=STAMP,prior_zip=old)
            h=report["source_history"]
            self.assertEqual(report["journal"]["status"],
                             "IDENTICAL_SOURCE_SNAPSHOT_ALREADY_SEALED")
            self.assertEqual(h["status"],"FULL_SOURCE_BYTES_VERIFIED")
            self.assertEqual(h["raw_source_blob_count"],2)
            self.assertEqual(h["legacy_source_blobs_recovered"],2)
            self.assertEqual(h["total_journal_source_digests"],2)
            for source,blob in data.items():
                digest=sha256(blob).hexdigest()
                self.assertEqual((root/"next"/"history"/source/(digest+".txt")).read_bytes(),
                                 blob)
            self.assertTrue(report["journal"]["earlier_full_source_bytes_preserved"])
            self.assertEqual(report["finality_verified"],0)

    def test_new_revision_preserves_both_source_versions_across_two_drive_cycles(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            first=fixture()
            second=fixture(changed=True)
            old=root/"old.zip"
            write_old_zip(old,from_first_snapshot(first),first)
            report=run(SPEC,root/"next",fetcher=as_fetcher(second),
                       stamp=STAMP,prior_zip=old)
            self.assertEqual(report["journal"]["status"],
                             "SAME_FILE_CREATION_DATES_CHANGED_BYTES_HOLD")
            self.assertEqual(report["source_history"]["raw_source_blob_count"],3)
            self.assertEqual(report["source_history"]["status"],"FULL_SOURCE_BYTES_VERIFIED")
            self.assertEqual(report["journal"]["journal_events"],2)
            future=root/"future.zip"
            zipped_result(future,root/"next")
            third=run(SPEC,root/"third",fetcher=as_fetcher(second),
                      stamp=STAMP,prior_zip=future)
            self.assertEqual(third["journal"]["journal_events"],2)
            self.assertEqual(third["source_history"]["raw_source_blob_count"],3)
            self.assertEqual(third["source_history"]["legacy_source_blobs_recovered"],0)
            self.assertEqual(third["source_history"]["status"],"FULL_SOURCE_BYTES_VERIFIED")
            for source in first:
                digest=sha256(first[source]).hexdigest()
                self.assertEqual((root/"third"/"history"/source/(digest+".txt")).read_bytes(),
                                 first[source])
            self.assertEqual(third["finality_verified"],0)

    def test_prior_source_blob_tampering_is_hard_rejection(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=fixture()
            old=root/"corrupt.zip"
            bad=dict(source)
            bad["nasdaqlisted"]=bad["nasdaqlisted"].replace(b"Test QQQ",b"Fake QQQ")
            write_old_zip(old,from_first_snapshot(source),bad)
            with self.assertRaisesRegex(ValueError,"DIGEST_MISMATCH"):
                run(SPEC,root/"out",fetcher=as_fetcher(source),
                    stamp=STAMP,prior_zip=old)

    def test_historical_missing_legacy_raw_is_explicit_hold(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            first,second=fixture(),fixture(changed=True)
            old_chain=from_first_snapshot(first)
            second_report=one_snapshot(SPEC,second,fetched_at=STAMP)
            full_chain,_=save_journal(old_chain,second_report,
                                      prior_status="CONTINUED")
            archive=root/"legacy-only-latest.zip"
            write_old_zip(archive,full_chain,second)
            report=run(SPEC,root/"out",fetcher=as_fetcher(second),
                       stamp=STAMP,prior_zip=archive)
            self.assertEqual(report["source_history"]["status"],
                             "LEGACY_SOURCE_BYTES_MISSING_HOLD")
            self.assertEqual(len(report["source_history"]["missing_historic_source_digests"]),1)
            self.assertEqual(report["status"],
                             "OFFICIAL_DIRECTORY_SOURCE_HISTORY_INCOMPLETE_HOLD")
            self.assertFalse(report["journal"]["earlier_full_source_bytes_preserved"])
            self.assertEqual(report["finality_verified"],0)

    def test_source_fetch_failure_keeps_valid_prior_full_bytes(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=fixture()
            old=root/"old.zip"
            write_old_zip(old,from_first_snapshot(source),source)
            def fail(_):
                raise ValueError("network unavailable")
            result=run(SPEC,root/"out",fetcher=fail,stamp=STAMP,prior_zip=old)
            self.assertEqual(result["status"],"OFFICIAL_DIRECTORY_SOURCE_UNAVAILABLE_HOLD")
            self.assertEqual(result["source_history"]["status"],"FULL_SOURCE_BYTES_VERIFIED")
            self.assertEqual(result["source_history"]["raw_source_blob_count"],2)
            self.assertTrue((root/"out"/"snapshot_journal.jsonl").is_file())

    def test_missing_prior_archive_cannot_silently_start_fresh_chain(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=run(SPEC,root/"out",fetcher=as_fetcher(fixture()),
                       stamp=STAMP,prior_zip=root/"no-file.zip")
            self.assertEqual(result["status"],"OFFICIAL_DIRECTORY_SOURCE_HISTORY_INCOMPLETE_HOLD")
            self.assertEqual(result["journal"]["status"],"PRIOR_DRIVE_ARCHIVE_MISSING_HOLD")
            self.assertEqual(result["journal"]["journal_events"],0)
            self.assertEqual(result["finality_verified"],0)

    def test_prior_full_history_blob_corruption_rejected(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=fixture()
            chain=from_first_snapshot(source)
            old=root/"old.zip"
            with ZipFile(old,"w") as z:
                z.writestr(JOURNAL_MEMBER,json.dumps(chain[0])+"\n")
                for key,blob in source.items():
                    digest=sha256(blob).hexdigest()
                    z.writestr(member_for(key,digest),b"DELIBERATELY CORRUPTED")
            with self.assertRaisesRegex(ValueError,"DIGEST_MISMATCH"):
                preserve(old,chain,None,root/"out")

    def test_preview_makes_no_history_seals(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=run(SPEC,root/"out",fetcher=as_fetcher(fixture()),
                       stamp=STAMP,preview=True)
            self.assertEqual(result["source_history"]["status"],"PR_PREVIEW_UNSEALED")
            self.assertFalse((root/"out"/"history").exists())
            self.assertFalse((root/"out"/"snapshot_journal.jsonl").exists())


if __name__=="__main__":
    unittest.main()
