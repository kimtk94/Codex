import datetime as dt
import unittest
from latest_source_sync import shape, snapshot_readback_equal
from latest_four_formats import select, FORMATS
from project_status_sync import latest_flags
class LatestTests(unittest.TestCase):
    def test_snapshot_readback_accepts_only_trimmed_trailing_empty_cells(self):
        expected=[["Project Number","Outstanding Status","Comment"],
                  ["X0001","Open",""], ["X0002","Closed","Note"]]
        observed=[["Project Number","Outstanding Status","Comment"],
                  ["X0001","Open"], ["X0002","Closed","Note"]]
        self.assertTrue(snapshot_readback_equal(expected,observed))
        self.assertTrue(snapshot_readback_equal(expected,expected))

    def test_snapshot_readback_fails_on_same_row_count_cell_drift(self):
        expected=[["Project Number","Status","Amount"],
                  ["X0001","Open","1000"],["X0002","Closed","3000"]]
        altered=[["Project Number","Status","Amount"],
                 ["X0001","","1000"],["X0002","Closed","3000"]]
        self.assertFalse(snapshot_readback_equal(expected,altered))
        altered[1]=["X0001","Open","2000"]
        self.assertFalse(snapshot_readback_equal(expected,altered))
        altered[1]=expected[2]
        altered[2]=expected[1]
        self.assertFalse(snapshot_readback_equal(expected,altered))

    def test_snapshot_readback_refuses_extra_nonempty_cells_and_rows(self):
        expected=[["A","B"],["1","2"]]
        self.assertFalse(snapshot_readback_equal(expected,[["A","B","PRIVATE"],["1","2"]]))
        self.assertFalse(snapshot_readback_equal(expected,[["A","B"],["1","2"],["3","4"]]))
        self.assertFalse(snapshot_readback_equal(expected,[["A","B"]]))
        self.assertFalse(snapshot_readback_equal([],[]))
        self.assertFalse(snapshot_readback_equal(expected,[("A","B"),["1","2"]]))

    def test_publish_refuses_unchanged_row_count_with_changed_status(self):
        from unittest.mock import patch
        from latest_source_sync import publish
        from urllib.parse import unquote
        confidential="PRIVATE_CLIENT_ID_SHOULD_NOT_LOG"
        source={"Payment Outstanding":{
            "title":"Feishu Latest Outstanding",
            "headers":["Project Number","Status"],
            "rows":[[confidential,"UNPAID"]],
            "source_date":"2026-11-11",
            "source_id":"test_tab",
            "schema":"HEADER_MATCHED",
            "synced_at":"2026-11-17T08:30:00+09:00"
        }}
        def fake_google_api(session,method,suffix,**kw):
            if method=="POST":
                return {}
            if suffix.startswith("?fields="):
                return {"sheets":[
                    {"properties":{"title":"Feishu Latest Outstanding","sheetId":100,"gridProperties":{"rowCount":10,"columnCount":2}}},
                    {"properties":{"title":"Feishu Source Manifest","sheetId":101,"gridProperties":{"rowCount":10,"columnCount":7}}}
                ]}
            if method=="GET" and suffix.startswith("/values/"):
                if "Feishu Latest Outstanding" in unquote(suffix):
                    return {"values":[["Project Number","Status"],[confidential,""]]}
                return {"values":[["Source","Source Date","Synced At KST","Source ID","Rows","Schema","Meaning"],
                        ["Payment Outstanding","2026-11-11","2026-11-17T08:30:00+09:00",
                         "test_tab","1","HEADER_MATCHED",
                         "Outstanding snapshot; absence is not payment evidence"]]}
            raise AssertionError("UNKNOWN_SYNTHETIC_CALL")
        with patch("project_status_sync.api",side_effect=fake_google_api):
            with self.assertRaisesRegex(RuntimeError,"READBACK_CONTENT_MISMATCH") as caught:
                publish(object(),source)
        self.assertNotIn(confidential,str(caught.exception))

    def test_title_rows_and_duplicate_headers(self):
        h,r,s=shape([['Company report'],['Project Number','Amount','Amount'],['X123456','10','20']])
        self.assertEqual(s,'HEADER_MATCHED');self.assertEqual(h,['Project Number','Amount','Amount [2]']);self.assertEqual(len(r),1)
    def test_unknown_schema_is_preserved_for_review(self):
        h,r,s=shape([['a','b'],['c','d']]);self.assertEqual(s,'RAW_GRID_REVIEW');self.assertEqual(len(r),2)
    def test_empty_fails(self):
        with self.assertRaises(RuntimeError):shape([])
    def test_latest_tie_blocks(self):
        names={'Payment Outstanding':'Payment Outstanding','eTax Invoice':'eTax - KR Invoice','Payment Receipt':'Payment Receipt','Prepayments':'Prepayments'}
        rows=[{'sheet_id':str(i),'title':name+' 10.26'} for i,name in enumerate(names.values())]
        rows.append({'sheet_id':'duplicate','title':'Payment Outstanding 10.26'})
        with self.assertRaises(RuntimeError):select(rows,dt.date(2026,10,27))
    def test_no_issuance_inferred_from_etax_membership(self):
        ss={k:{'headers':['Project Number','Invoice Status'],'schema':'HEADER_MATCHED','rows':[['X123456','issued']] if k=='eTax Invoice' else []} for k in ['Payment Outstanding','eTax Invoice']}
        out=latest_flags(ss,[], 'now');self.assertEqual(out[1][1],'UNKNOWN');self.assertEqual(out[1][2],'UNKNOWN')
    def test_explicit_unissued_and_outstanding(self):
        ss={k:{'headers':['Project Number','Invoice Status'],'schema':'HEADER_MATCHED','rows':[['X123456','not issued']]} for k in ['Payment Outstanding','eTax Invoice']}
        out=latest_flags(ss,[], 'now');self.assertEqual(out[1][1:4],['YES','YES','P0_BOTH'])
    def test_prior_missing_is_unknown(self):
        ss={k:{'headers':[],'schema':'RAW_GRID_REVIEW','rows':[]} for k in ['Payment Outstanding','eTax Invoice']}
        out=latest_flags(ss,[['X123456']], 'now');self.assertEqual(out[1][1:4],['UNKNOWN','UNKNOWN','REVIEW_CARRYOVER'])
if __name__=='__main__':unittest.main()
