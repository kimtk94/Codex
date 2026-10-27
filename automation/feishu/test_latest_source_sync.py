import datetime as dt
import unittest
from latest_source_sync import shape
from latest_four_formats import select, FORMATS
from project_status_sync import latest_flags
class LatestTests(unittest.TestCase):
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
