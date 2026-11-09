#!/usr/bin/env python3
"""No cross-owned Feishu record writes in the two independent Actions."""
import unittest
from unittest import mock
import sales_metrics_sync as m

def output():
    return {
        "Weekly Quote KPI":[{"Week Start":"2026-10-30","Chart Window":"HISTORY"}],
        "Monthly Tax Invoice":[{"Source Key":"INVOICE_MONTH:2026-10"}],
        "Project SIF Monitor":[{"Source Key":"SIF:1"}],
        "Project Progress Board":[{"Source Key":"PROJECT:1"}],
    }

class ScopeWriteTests(unittest.TestCase):
    def base(self,scope):
        return mock.patch.dict(m.os.environ,{
            "FEISHU_BASE_APP_TOKEN":m.EXPECTED_BASE,
            "FEISHU_METRIC_MODE":"apply",
            "FEISHU_METRIC_SCOPE":scope
        })
    def test_quote_writes_quote_kpi_and_review_only(self):
        paths={key:"/t/"+key for key in m.SCHEMAS}
        with self.base("quote"), \
             mock.patch.object(m,"sheet_sources",return_value={}), \
             mock.patch.object(m,"prepare_data",return_value=output()), \
             mock.patch.object(m,"auth",return_value=("token","/root")), \
             mock.patch.object(m,"ensure_tables",return_value=paths), \
             mock.patch.object(m,"setup_views"), \
             mock.patch.object(m,"board_list_with_retry",return_value=[]), \
             mock.patch.object(m,"quote_manual_overrides",return_value={}), \
             mock.patch.object(m,"build_quote_review",return_value=[]), \
             mock.patch.object(m,"weekly_rows",return_value=output()["Weekly Quote KPI"]), \
             mock.patch.object(m,"sync_quote_review",return_value={}) as qr, \
             mock.patch.object(m,"sync_board_table") as board, \
             mock.patch.object(m,"sync_table",return_value=(0,0,1)) as sink:
            m.main()
        qr.assert_called_once()
        board.assert_not_called()
        self.assertEqual(sink.call_count,1)
        self.assertEqual(sink.call_args.args[1],paths["Weekly Quote KPI"])
    def test_operations_never_write_weekly_or_monthly(self):
        paths={key:"/t/"+key for key in m.SCHEMAS}
        audit={key:0 for key in (
            "projects_with_invoices","projects_source_receipt_complete",
            "my_verified_invoice_projects","other_sales_invoice_projects",
            "owner_review_projects","projects_review_required")}
        with self.base("operations"), \
             mock.patch.object(m,"sheet_sources",return_value={}), \
             mock.patch.object(m,"project_rows",return_value=output()["Project SIF Monitor"]), \
             mock.patch.object(m,"prepare_project_board",return_value=output()["Project Progress Board"]), \
             mock.patch.object(m,"build_payment_evidence",return_value=({},{},audit)), \
             mock.patch.object(m,"auth",return_value=("token","/root")), \
             mock.patch.object(m,"ensure_tables",return_value=paths), \
             mock.patch.object(m,"setup_views"), \
             mock.patch.object(m,"sync_quote_review") as qr, \
             mock.patch.object(m,"sync_board_table",return_value=(0,0,1)) as board, \
             mock.patch.object(m,"sync_table",return_value=(0,0,1)) as sink:
            m.main()
        qr.assert_not_called()
        board.assert_called_once()
        self.assertEqual(sink.call_count,1)
        self.assertEqual(sink.call_args.args[1],paths["Project SIF Monitor"])

if __name__=="__main__":
    unittest.main()
