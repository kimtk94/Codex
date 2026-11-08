#!/usr/bin/env python3
"""Only canonical issued monthly rows can mutate Feishu Monthly Tax Invoice."""
import copy
import unittest

from qq_mail_ingest import SafeError
from monthly_revenue_actual_sync import (verify_monthly_readback,
                                          index_records,safe_existing_fields,
                                          validate_mail_only_existing)
from monthly_revenue_canonical import evidence_rows
from test_monthly_revenue_canonical import source


class MonthlyActualSyncTests(unittest.TestCase):
    def test_erp_manual_and_forecast_records_are_rejected_from_source_table(self):
        valid=[{"record_id":"r1","fields":{"Source Key":"INVOICE:2026-10"}}]
        validate_mail_only_existing(valid)
        for bad in ("ERP_ETAX:2026-10:20910000208+20910000209",
                    "MANUAL:2026-10","FORECAST:2026-10",
                    "QUOTE:2026-10","INVOICE:2026-13"):
            with self.subTest(bad=bad):
                rows=valid+[{"record_id":"r2",
                             "fields":{"Source Key":bad,"Month":"2026-10"}}]
                with self.assertRaisesRegex(SafeError,"NON_MAIL_SOURCE"):
                    validate_mail_only_existing(rows)

    def test_readback_fails_if_erp_row_would_enter_chart(self):
        valid=[{"record_id":"r1","fields":{"Source Key":"INVOICE:2026-10",
               "Invoice Count":48}}]
        after=valid+[{"record_id":"r2",
                      "fields":{"Source Key":"ERP_ETAX:2026-10:manual",
                                "Month":"2026-10","Invoice Count":1}}]
        with self.assertRaisesRegex(SafeError,"NON_MAIL_SOURCE"):
            verify_monthly_readback(valid,after,[])

    def test_readback_preserves_all_unrelated_historical_months(self):
        desired=evidence_rows(source())
        historical={"record_id":"recHistory",
                    "fields":{"Source Key":"INVOICE:2026-09",
                              "Month":"2026-09","Invoice Count":46,
                              "Net Revenue M KRW":159.2135,
                              "Coverage Status":"SOURCE_SCOPE_MATCH"}}
        before=[historical,{"record_id":"recOctober",
               "fields":{"Source Key":"INVOICE:2026-10","Month":"2026-10",
                         "Invoice Count":24,"Net Revenue M KRW":51.485}}]
        after=[copy.deepcopy(historical),
               {"record_id":"recOctober","fields":dict(desired[1])},
               {"record_id":"recNovember","fields":dict(desired[0])}]
        verify_monthly_readback(before,after,desired)
        self.assertEqual(safe_existing_fields(before[0]),
                         safe_existing_fields(after[0]))

    def test_readback_rejects_any_history_mutation(self):
        desired=evidence_rows(source())
        before=[{"record_id":"recHistory",
                 "fields":{"Source Key":"INVOICE:2026-09","Invoice Count":46}}]
        after=copy.deepcopy(before)
        after[0]["fields"]["Invoice Count"]=47
        after.extend([{"record_id":"recX"+str(i),"fields":dict(item)}
                      for i,item in enumerate(desired)])
        with self.assertRaisesRegex(SafeError,"UNRELATED_RECORD_CHANGED"):
            verify_monthly_readback(before,after,desired)

    def test_readback_rejects_missing_or_wrong_canonical_value(self):
        desired=evidence_rows(source())
        before=[]
        after=[{"record_id":"recX"+str(i),"fields":dict(item)}
               for i,item in enumerate(desired)]
        after[0]["fields"]["Net Revenue M KRW"]=0
        with self.assertRaisesRegex(SafeError,"READBACK_MISMATCH"):
            verify_monthly_readback(before,after,desired)

    def test_missing_old_records_are_not_silently_accepted(self):
        desired=evidence_rows(source())
        before=[{"record_id":"recHistory",
                 "fields":{"Source Key":"INVOICE:2026-09","Invoice Count":46}}]
        after=[{"record_id":"recX"+str(i),"fields":dict(item)}
               for i,item in enumerate(desired)]
        with self.assertRaisesRegex(SafeError,"UNEXPECTED_RECORD_REMOVAL"):
            verify_monthly_readback(before,after,desired)

    def test_duplicate_source_key_rejected(self):
        data=[{"record_id":"a","fields":{"Source Key":"INVOICE:2026-10"}},
              {"record_id":"b","fields":{"Source Key":"INVOICE:2026-10"}}]
        with self.assertRaisesRegex(SafeError,"DUPLICATE"):
            index_records(data)


if __name__=="__main__":
    unittest.main()
