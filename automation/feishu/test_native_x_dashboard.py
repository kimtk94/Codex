#!/usr/bin/env python3
"""Owner-scoped X dashboard never ranks or invents per-X progress."""
import unittest
from native_x_dashboard import WIDGETS,CURRENT,MINE,find_block
from sync_x_project_registry import VIEWS
from x_project_lineage import LINK_SCHEMAS

class NativeXDashboardTests(unittest.TestCase):
    def test_every_numeric_chart_uses_current_owner_source(self):
        for name,kind,config in WIDGETS:
            if kind=="text":continue
            conditions=config["filter"]["conditions"]
            self.assertEqual(config["filter"]["conjunction"],"and")
            self.assertIn(CURRENT,conditions,name)
            self.assertIn(MINE,conditions,name)
            self.assertNotEqual(kind,"ranking")
            self.assertIn(config["table_name"],
                {"X Project Registry","X Invoice Ledger"})
    def test_integer_project_sample_and_invoice_count_cards(self):
        for name,kind,config in WIDGETS:
            if kind=="statistics":
                self.assertEqual(config["number_format"],
                    {"formatName":"digital","precision":0},name)
    def test_x_registry_never_inherits_amea_progress(self):
        fields={name for name,_ in LINK_SCHEMAS["X Project Registry"]}
        self.assertNotIn("Progress %",fields)
        self.assertIn("Progress Bar",fields)
        self.assertIn("AMEA Link State",fields)
        self.assertIn("SAM Linked",fields)
        self.assertIn("Record State",fields)
    def test_personal_views_and_review_views_are_separated(self):
        for table,viewname in (("X Project Registry","내 X 프로젝트"),
                               ("X Invoice Ledger","내 X Invoice")):
            views=dict(VIEWS[table])
            self.assertIn(("Owner Scope","MY_VERIFIED"),views[viewname])
            self.assertIn(("Record State","CURRENT"),views[viewname])
        self.assertIn("공유 SAM 검토",dict(VIEWS["AMEA H X SAM Link"]))
    def test_detail_blocks_unique(self):
        self.assertEqual(len({name for name,_,_ in WIDGETS}),len(WIDGETS))
        assert find_block({"items":[{"name":"a","block_id":"cht001"}]},"a")
if __name__=="__main__":unittest.main()
