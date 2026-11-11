import csv
import datetime as dt
import gzip
import tempfile
import unittest
from pathlib import Path

from backfill_upbit import as_utc, collect, write_monthly

def candle(time_utc, price=100):
    return {'candle_date_time_utc':time_utc,'opening_price':price,
            'high_price':price+1,'low_price':price-1,'trade_price':price,
            'candle_acc_trade_volume':2,'candle_acc_trade_price':200}

class BackfillTests(unittest.TestCase):
    def test_collect_preserves_no_trade_gap_and_unique_times(self):
        a=as_utc('2026-10-29T00:00:00Z')
        b=as_utc('2026-10-29T00:03:00Z')
        received=[]
        def fetch(market,unit,cursor):
            received.append((market,unit,cursor))
            return [candle('2026-10-29T00:02:00'),candle('2026-10-29T00:00:00'),
                    candle('2026-10-29T00:02:00')]
        rows,pages=collect('KRW-BTC',1,a,b,max_pages=4,fetch=fetch,sleeper=lambda _:None)
        self.assertEqual(pages,1)
        self.assertEqual(len(rows),2)
        self.assertEqual([r['time_utc'][:19] for r in rows],['2026-10-29T00:00:00','2026-10-29T00:02:00'])
        self.assertTrue(all(r['volume']==2 for r in rows))
        with tempfile.TemporaryDirectory() as d:
            paths=write_monthly(Path(d),'KRW-BTC',1,rows)
            self.assertEqual(len(paths),1)
            with gzip.open(Path(d)/paths[0],'rt',newline='') as handle:
                loaded=list(csv.DictReader(handle))
            self.assertEqual(len(loaded),2)
            self.assertEqual(loaded[0]['unit_min'],'1')

    def test_duplicate_response_cursor_abort(self):
        a=as_utc('2026-10-29T00:00:00Z')
        b=as_utc('2026-10-29T00:03:00Z')
        with self.assertRaisesRegex(RuntimeError,'Cursor'):
            collect('KRW-ETH',1,a,b,max_pages=4,
                    fetch=lambda *args:[candle('2026-10-29T00:03:00')],
                    sleeper=lambda _:None)

    def test_page_cap_halts_incomplete_backfill(self):
        a=as_utc('2026-10-29T00:00:00Z')
        b=as_utc('2026-10-29T00:03:00Z')
        with self.assertRaisesRegex(RuntimeError,'PAGE_CAP_HIT'):
            collect('KRW-ETH',1,a,b,max_pages=1,
                    fetch=lambda *args:[candle('2026-10-29T00:02:00')],
                    sleeper=lambda _:None)

if __name__=='__main__':
    unittest.main()
