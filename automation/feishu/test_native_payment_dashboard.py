#!/usr/bin/env python3
import unittest
from native_payment_dashboard_cli import (
  PAYMENT_BLOCKS,PROJECT_BLOCKS,filter_lane,find_block,block_id
)

class NativePaymentDashboardTests(unittest.TestCase):
  def test_production_scope_contains_active_lane_on_each_project_widget(self):
    self.assertEqual(len(PROJECT_BLOCKS),6)
    for name,filt in PROJECT_BLOCKS.items():
      self.assertEqual(filt["conjunction"],"and")
      self.assertIn({"field_name":"Workflow Lane","operator":"is","value":"PRODUCTION_ACTIVE"},
                    filt["conditions"])
    condition=PROJECT_BLOCKS["진행률 확인 건수"]["conditions"]
    self.assertIn({"field_name":"Progress %","operator":"isNotEmpty"},condition)
  def test_payment_dashboard_all_details_exclude_paid_archive(self):
    for name,typ,config in PAYMENT_BLOCKS:
      if typ=="text":continue
      conditions=(config.get("filter") or {}).get("conditions") or []
      lane=[c["value"] for c in conditions if c["field_name"]=="Workflow Lane"]
      if name=="입금 확인 · 보관 건수":
        self.assertEqual(lane,["PAID_ARCHIVED"])
      else:self.assertEqual(lane,["PAYMENT_FOLLOWUP"])
    self.assertTrue(any(
        x[0]=="결제 대기 · Quote Full Name" and
        x[2]["group_by"][0]["field_name"]=="Project Display Name"
        for x in PAYMENT_BLOCKS))
  def test_feishu_native_block_id_and_duplicates(self):
    obj={"items":[{"name":"Test","block_id":"chtABC001"}]}
    self.assertEqual(find_block(obj,"Test")["block_id"],"chtABC001")
    self.assertIsNone(find_block(obj,"Other"))
    with self.assertRaisesRegex(RuntimeError,"DUPLICATE"):
      find_block({"items":[{"name":"Test","block_id":"cht1"},
                           {"name":"Test","block_id":"cht2"}]},"Test")
  def test_source_tables_are_original_base(self):
    self.assertTrue(all(
       x[2].get("table_name")=="Project Progress Board"
       for x in PAYMENT_BLOCKS if x[1]!="text"))
if __name__=="__main__":unittest.main()
