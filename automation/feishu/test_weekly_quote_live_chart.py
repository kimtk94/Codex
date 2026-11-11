#!/usr/bin/env python3
"""Synthetic-only proof of source-driven Weekly Quote checkbox filtering."""
import copy
import datetime as dt
import unittest
from decimal import Decimal as D

from qq_mail_ingest import SafeError
import weekly_quote_live_chart as q

WEEKS=[(dt.date(2026,10,9)+dt.timedelta(days=7*i)).isoformat()
       for i in range(5)]

def review(week,quote,flag=False,active=True,amount=2.5,window=None):
    return {"fields":{
        "Source Key":"QUOTE_REVIEW:a0P"+str(quote).zfill(12),
        "Week Start":week,"Chart Window":window or q.WINDOW,
        "Quote Status":"ACTIVE" if active else "INACTIVE",
        "Approved AND Active":"YES" if active else "NO",
        "SFDC IsActive":"1" if active else "0",
        "합산 제외":flag,
        q.COUNT_FIELD:1,
        q.AMOUNT_FIELD:amount,
    }}

def fixtures():
    items=[review("2026-09-01",i,window="HISTORY")
           for i in range(1,111)]
    for i,week in enumerate(WEEKS):
        items.append(review(week,200+i,amount=2.5))
        items.append(review(week,300+i,flag=True,amount=7))
        items.append(review(week,400+i,active=False,amount=9))
    kpis=[{"fields":{
        "Week Start":w,"Chart Window":q.WINDOW,
        "Included Quote Count":1,
        "Calculated Quote Value K USD":2.5
    }} for w in WEEKS]
    return items,kpis

class LiveQuoteTests(unittest.TestCase):
    def test_direct_table_checkbox_filter_and_two_sums(self):
        cfg=q.config()
        self.assertEqual(cfg["table_name"],"Weekly Quote Review")
        self.assertEqual(cfg["series"],[
            {"field_name":"실시간 집계용 건수","rollup":"SUM"},
            {"field_name":"참고 금액 K USD","rollup":"SUM"}])
        self.assertNotIn("count_all",cfg)
        filters=cfg["filter"]["conditions"]
        self.assertIn({"field_name":"합산 제외","operator":"is","value":False},filters)
        self.assertEqual(len(filters),5)
        self.assertEqual(cfg["group_by"][0]["field_name"],"Week Start")

    def test_one_time_source_and_kpi_parity(self):
        rows,kpis=fixtures()
        result=q.audit_rows(rows,kpis,True)
        self.assertEqual(result["week_count"],5)
        self.assertEqual(result["included_quote_count"],5)
        self.assertEqual(result["total_quote_rows"],125)
        self.assertEqual(result["amount_withheld_cases"],0)
        self.assertEqual(result["source_writes"],0)

    def test_checkbox_changes_live_without_stale_kpi_update(self):
        rows,kpis=fixtures()
        row=next(x for x in rows if x["fields"]["Week Start"]==WEEKS[-1]
                 and x["fields"]["합산 제외"] is False)
        self.assertTrue(q.matches_live(row["fields"]))
        row["fields"]["합산 제외"]=True
        self.assertFalse(q.matches_live(row["fields"]))
        # No scheduled KPI job has run, so strict one-time parity now fails.
        with self.assertRaisesRegex(SafeError,"INCLUDED_COUNT_PARITY_FAILED"):
            q.audit_rows(rows,kpis,True)
        # Native chart reads only the review rows: current count already fell.
        result=q.audit_rows(rows,kpis,False)
        self.assertEqual(result["included_quote_count"],4)

    def test_source_active_proof_never_inferred_from_checkbox(self):
        row=review(WEEKS[0],55,active=False)["fields"]
        self.assertFalse(q.matches_live(row))
        row["합산 제외"]=False
        self.assertFalse(q.matches_live(row))
        row["Quote Status"]="ACTIVE"
        self.assertFalse(q.matches_live(row))
        row["Approved AND Active"]="YES"
        self.assertFalse(q.matches_live(row))
        row["SFDC IsActive"]="1"
        self.assertTrue(q.matches_live(row))

    def test_missing_price_is_partial_not_zero_imputation(self):
        rows,kpis=fixtures()
        row=next(x for x in rows if x["fields"]["Week Start"]==WEEKS[-1]
                 and x["fields"]["합산 제외"] is False)
        row["fields"][q.AMOUNT_FIELD]=None
        # Another Quote retains a proven price; the missing one is not zero.
        rows.append(review(WEEKS[-1],9999,amount=2.5))
        kpis[-1]["fields"]["Included Quote Count"]=2
        result=q.audit_rows(rows,kpis,True)
        self.assertEqual(result["amount_withheld_cases"],1)

    def test_missing_numeric_counter_blocks_chart(self):
        rows,kpis=fixtures()
        del rows[0]["fields"][q.COUNT_FIELD]
        with self.assertRaisesRegex(SafeError,"COUNT_UNIT_NOT_BACKFILLED"):
            q.audit_rows(rows,kpis,False)

    def test_duplicate_immutable_quote_blocks(self):
        rows,kpis=fixtures()
        rows.append(copy.deepcopy(rows[1]))
        with self.assertRaisesRegex(SafeError,"SOURCE_KEY_INVALID_OR_DUPLICATE"):
            q.audit_rows(rows,kpis,False)

if __name__=="__main__":
    unittest.main()
