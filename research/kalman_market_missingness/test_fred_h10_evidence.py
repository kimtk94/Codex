import unittest
from fred_h10_evidence import classify_fred_h10, reconcile_fred_fx_nulls

class H10EvidenceTests(unittest.TestCase):
    def test_known_no_data(self):
        x=classify_fred_h10('2020-11-27','DEXKOUS')
        self.assertEqual(x['evidence_class'],'ARCHIVED_H10_ND')
        self.assertFalse(x['historical_imputation_allowed'])

    def test_board_weather_closure_not_silent_fill(self):
        x=classify_fred_h10('2019-02-20','DTWEXBGS')
        self.assertEqual(x['evidence_class'],'FED_BOARD_CLOSED_WEATHER')
        self.assertFalse(x['pit_training_eligible'])

    def test_broad_archive_conflict_only_that_series(self):
        self.assertEqual(classify_fred_h10('2019-12-24','DTWEXBGS')['evidence_class'],
                         'PUBLISHED_H10_BROAD_INDEX_CONFLICT')
        self.assertEqual(classify_fred_h10('2019-12-24','DEXKOUS')['evidence_class'],
                         'UNCLASSIFIED')

    def test_unknown_stays_unknown(self):
        self.assertEqual(classify_fred_h10('2026-01-14','DEXKOUS')['evidence_class'],
                         'UNCLASSIFIED')

    def test_exact_16_rows(self):
        by_date={
          '2017-01-20':['DEXKOUS','DTWEXBGS'],
          '2018-03-02':['DTWEXBGS'],
          '2018-03-21':['DTWEXBGS'],
          '2018-12-24':['DEXKOUS'],
          '2019-01-14':['DEXKOUS','DTWEXBGS'],
          '2019-02-20':['DEXKOUS','DTWEXBGS'],
          '2019-12-24':['DTWEXBGS'],
          '2020-11-27':['DEXKOUS','DTWEXBGS'],
          '2020-12-24':['DEXKOUS','DTWEXBGS'],
          '2021-01-20':['DEXKOUS','DTWEXBGS']
        }
        records=[{'date':date,'indicator':indicator} for date,indicators in by_date.items() for indicator in indicators]
        detail,s=reconcile_fred_fx_nulls(records)
        self.assertEqual(len(detail),16)
        self.assertEqual(s['official_nd_or_board_closure_rows'],15)
        self.assertEqual(s['official_archive_conflict_rows'],1)
        self.assertEqual(s['unclassified_rows'],0)

if __name__=='__main__': unittest.main()