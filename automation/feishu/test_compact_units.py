#!/usr/bin/env python3
"""Regress display units, count precision and curated navigation."""
import unittest
from unittest import mock
from number_format_cli import COUNTS,payload,read_field
from native_dashboard_cli import BLOCKS,LEGACY_COMBO_NAMES
from native_payment_dashboard_cli import PAYMENT_BLOCKS
from sales_native_home import MENUS,PINNED_KEYS,CURATED_DISPLAY,ARCHIVE_DISPLAY

class CompactDisplayTests(unittest.TestCase):
    def test_whole_number_field_formatter_preserves_metadata(self):
        field={"name":"Approved Quote Count","type":"number",
               "style":{"type":"plain","precision":2,
                        "percentage":False,"thousands_separator":True},
               "description":"Source count"}
        result=payload(field)
        self.assertEqual(result["style"]["precision"],0)
        self.assertEqual(result["description"],"Source count")
        self.assertTrue(result["style"]["thousands_separator"])
        self.assertEqual(result["type"],"number")
        self.assertEqual(result["name"],"Approved Quote Count")
        self.assertEqual(field["style"]["precision"],2)
    def test_numeric_source_audit_is_faill_closed(self):
        with mock.patch("number_format_cli.cli",return_value={
            "field":{"name":"Approved Quote Count","type":"text"}}):
            with self.assertRaisesRegex(RuntimeError,"TYPE_OR_NAME"):
                read_field("Weekly Quote KPI","Approved Quote Count")
        self.assertEqual(len(COUNTS),6)
    def test_krw_is_millions_usd_is_thousands(self):
        combos=[(n,c) for n,t,c in BLOCKS if t=="combo"]
        self.assertEqual(len(combos),2)
        for name,config in combos:
            field=config["series"][1]["field_name"]
            if "(M KRW)" in name:
                self.assertEqual(field,"Verified Quote Value M KRW")
            else:
                self.assertIn("(K USD)",name)
                self.assertEqual(field,"Verified Quote Value K USD")
        monthly=next(c for n,t,c in BLOCKS if n=="월별 Revenue · VAT 제외")
        self.assertEqual(monthly["series"][0]["field_name"],
                         "Net Revenue M KRW Ex VAT")
        self.assertEqual(LEGACY_COMBO_NAMES[
            "KOREA · Quote Count / Value (M KRW)"],
            "KOREA · Quote Count / Value (KRW)")
    def test_payment_gross_and_balance_display_in_millions(self):
        money=[c["series"][0]["field_name"] for _,t,c in PAYMENT_BLOCKS
               if "series" in c]
        self.assertIn("Invoice Gross M KRW",money)
        self.assertIn("Outstanding Balance M KRW",money)
        self.assertFalse(any(x=="Invoice Gross KRW" for x in money))
    def test_curated_home_is_only_twelve_operational_routes(self):
        self.assertEqual(len(PINNED_KEYS),12)
        keys={x[0] for x in MENUS}
        self.assertTrue(PINNED_KEYS.issubset(keys))
        self.assertIn("PAYMENT_FOLLOWUP",PINNED_KEYS)
        self.assertIn("X_URGENT",PINNED_KEYS)
        self.assertNotIn("X_SAMPLE_REVIEW",PINNED_KEYS)
        self.assertNotIn("MAIL_HISTORY",PINNED_KEYS)
        self.assertNotEqual(CURATED_DISPLAY,ARCHIVE_DISPLAY)
if __name__=="__main__": unittest.main()
