#!/usr/bin/env python3
"""Isolated regression tests for Feishu chart-only dashboard shortcuts."""
import unittest
from unittest import mock
import shortcut_chart_dashboards as s


class ChartShortcutTests(unittest.TestCase):
    def test_charts_match_real_source_configs(self):
        self.assertEqual(len(s.CHARTS),2)
        by_key={key:(kind,source) for key,_,_,_,_,kind,source in s.CHARTS}
        self.assertEqual(by_key,{
            "MONTHLY_TREND":("line","Monthly Tax Invoice"),
            "WEEKLY_TREND":("combo","Weekly Quote Review"),
        })
        for _,_,_,chart,note,kind,source in s.CHARTS:
            components=s.expected_components(chart,note,kind,source)
            self.assertEqual(components[0][1],kind)
            self.assertEqual(components[0][2]["table_name"],source)
            self.assertEqual(components[1][1],"text")
            if kind=="line":
                self.assertEqual(components[2][0],s.MONTHLY_LIST_NAME)
                self.assertEqual(components[2][1],"ranking")
                self.assertEqual(components[2][2]["table_name"],"Monthly Tax Invoice")
                self.assertEqual(components[2][2]["series"][0]["field_name"],"Net Revenue M KRW")

    def test_missing_widgets_created_then_verified(self):
        name,kind,config=s.expected_components(
            s.CHARTS[0][3],s.CHARTS[0][4],"line","Monthly Tax Invoice")[0]
        after={"items":[{"name":name,"type":kind,"block_id":"cht123"},
                        {"name":"월별 Revenue 표시 기준","type":"text","block_id":"cht456"},
                        {"name":s.MONTHLY_LIST_NAME,"type":"ranking","block_id":"cht789"}]}
        with mock.patch.object(s,"cli",side_effect=[
            {"items":[]},{"ok":True},{"ok":True},{"ok":True},after]) as cli:
            count=s.verify_components("blkNew",s.expected_components(
                s.CHARTS[0][3],s.CHARTS[0][4],"line","Monthly Tax Invoice"),True)
        self.assertEqual(count,3)
        self.assertEqual(cli.call_count,5)

    def test_existing_chart_avoids_writes(self):
        comp=s.expected_components(
            s.CHARTS[1][3],s.CHARTS[1][4],"combo","Weekly Quote Review")
        existing={"items":[{"name":name,"type":kind,"block_id":"cht"+str(i)}
                          for i,(name,kind,_) in enumerate(comp)]}
        with mock.patch.object(s,"cli",return_value=existing) as cli:
            self.assertEqual(s.verify_components("blkOld",comp,True),0)
            self.assertEqual(cli.call_count,4)
            updates=[c for c in cli.call_args_list if c.args[0]=="+dashboard-block-update"]
            self.assertEqual(len(updates),2)

    def test_existing_weekly_editor_link_readback_passes_without_duplicate_widget(self):
        url="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tblReview&view=vewFive"
        components=s.expected_components(
            s.CHARTS[1][3],s.CHARTS[1][4],"combo","Weekly Quote Review",url)
        self.assertEqual(len(components),2)
        existing={"items":[{"name":name,"type":kind,"block_id":"cht"+str(i)}
                           for i,(name,kind,_) in enumerate(components)]}
        stored={"block":{"name":components[1][0],"type":"text",
                         "data_config":components[1][2]}}
        with mock.patch.object(s,"cli",side_effect=[
                existing,{"ok":True},{"ok":True},existing,stored]) as cli:
            self.assertEqual(s.verify_components("blkWeek",components,True),0)
        self.assertEqual(cli.call_count,5)

    def test_existing_weekly_editor_link_wrong_readback_blocks(self):
        url="https://ocnz4cb25scn.feishu.cn/base/IpMkbUD0vaFqtYs93a3csXtdn1b?table=tblReview&view=vewFive"
        components=s.expected_components(
            s.CHARTS[1][3],s.CHARTS[1][4],"combo","Weekly Quote Review",url)
        existing={"items":[{"name":name,"type":kind,"block_id":"cht"+str(i)}
                           for i,(name,kind,_) in enumerate(components)]}
        stored={"block":{"name":components[1][0],"type":"text",
                         "data_config":{"text":"No editor link"}}}
        with mock.patch.object(s,"cli",side_effect=[
                existing,{"ok":True},{"ok":True},existing,stored]):
            with self.assertRaisesRegex(RuntimeError,"EDITABLE_LINK_READBACK_FAILED"):
                s.verify_components("blkWeek",components,True)

    def test_identity_and_types_fail_closed(self):
        with mock.patch.object(s,"cli",return_value={"items":[
            {"name":s.CHARTS[0][3],"type":"table","block_id":"cht001"}]}):
            with self.assertRaisesRegex(RuntimeError,"TYPE_MISMATCH"):
                s.verify_components("blkBad",s.expected_components(
                    s.CHARTS[0][3],s.CHARTS[0][4],"line","Monthly Tax Invoice"),True)

if __name__=="__main__":
    unittest.main()
