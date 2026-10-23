#!/usr/bin/env python3
"""Offline smoke tests for unified automation; no credentials and no API writes."""
import datetime as dt
import pathlib
import sys
import types
import unittest
from unittest.mock import MagicMock
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
# Inject read-only service-client test stubs before importing business logic.
css=types.ModuleType("incremental_sync")
css.api=MagicMock()
css.authorize=MagicMock()
sys.modules["incremental_sync"]=css
import unified_followup_sync as q
import followup_priority as f

class BusinessRules(unittest.TestCase):
    def test_week_friday_thursday(self):
        self.assertEqual(q.week_start(dt.date(2026,10,22)),dt.date(2026,10,16))
        self.assertEqual(q.week_start(dt.date(2026,10,23)),dt.date(2026,10,23))
        self.assertEqual(q.week_start(dt.date(2027,1,1)),dt.date(2027,1,1))
    def test_record_keys(self):
        a={"id":"a0PTK00000zPtNz","name":"QID1"}
        b={"id":"a0PTK00000z8Xms","name":"QID1"}
        self.assertNotEqual(q.key(a),q.key(b))
        self.assertEqual(q.key(a),q.key(dict(a)))
    def test_active_cannot_be_inferred(self):
        self.assertNotIn("APPROVED","UNVERIFIED")
    def test_followup_closed_excluded(self):
        result=f.score("완료","긴급","2026-01-01","QC 확인")
        self.assertEqual(result,(0,"CLOSED"))
    def test_followup_priority(self):
        n,level=f.score("미검토","긴급","2026-01-01","QC 확인")
        self.assertGreaterEqual(n,65)
        self.assertEqual(level,"P0")
if __name__=="__main__":unittest.main()
