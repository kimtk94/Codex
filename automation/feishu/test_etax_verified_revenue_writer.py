#!/usr/bin/env python3
"""One issued eTax document / two ERP lines, 48 QQ unchanged, no cash forecast."""
import copy
import os
import unittest
from unittest import mock
from qq_mail_ingest import SafeError
import etax_verified_revenue_writer as w


def sources():
    etax=[]
    for id,amount in (("20910000208",1287000),("20910000209",9317000)):
        etax.append({"ERP Invoice Number":id,
                     "Amount":str(amount),"Source":"Manual Invoice",
                     "Org Name":"Novogene KR","Currency":"KRW",
                     "Quotation Number":w.AMEA,"Project Number":w.X,
                     "CMS Invoice Num":"","Sales":"Kim Taehoon",
                     "GL Date":"46317"})
    return {
        "Feishu Latest eTax":etax,
        "SFDC Quote Export":[
            {"AMEA Quotation ID":w.AMEA,"IsActive":"1",
             "Quotation Name":w.QID,"Opportunity ID":w.OPP,
             "Account Name":"Changwon National University",
             "Contact Name":"성필모 SungPilMo"}],
        "SFDC Email Opportunities Raw":[
            {"Opportunity ID":w.OPP,"Opportunity Owner":"Kim Taehoon",
             "Stage":"Closed Won",
             "Account Name":"Changwon National University",
             "Main Contact":"성필모 SungPilMo"}],
        "CSS Tax Invoice Extract":[
            {"invoice_number":"209126001037","project_id":"AMEA2026101234",
             "subject":"unrelated","validation_status":"FILENAME_PARSED",
             "h_project_number":"H209SC26099999"}],
    }


def canonical():
    return {"record_id":"recQQ","fields":{
        "Source Key":"INVOICE:2026-10","Month":"2026-10",
        "Invoice Count":48,"Tax Invoice KRW Incl VAT":158541900,
        "Net Revenue KRW Ex VAT":144129000,
        "Net Revenue M KRW":144.129,
        "Net Revenue K USD":96.086,
        "Coverage Status":"QQ_ISSUED_VERIFIED_ERP_MANUAL_SCOPE_REVIEW"}}


def manual():
    return {"record_id":"recManual","fields":dict(w.manual_record())}


class VerifiedManualWriterTests(unittest.TestCase):
    def test_manual_record_is_one_certificate_not_two_erp(self):
        row=w.manual_record()
        self.assertEqual(row["Source Key"],w.MANUAL_KEY)
        self.assertEqual(row["Invoice Count"],1)
        self.assertEqual(row["Tax Invoice KRW Incl VAT"],10604000)
        self.assertEqual(row["Net Revenue KRW Ex VAT"],9640000)
        self.assertEqual(row["Net Revenue M KRW"],9.64)
        self.assertAlmostEqual(row["Net Revenue K USD"],6.4267,places=4)
        self.assertTrue("REVIEW" in row["Coverage Status"])
        self.assertIn("NOT proof of accrual revenue",row["Evidence"])
        self.assertNotIn("25.970",str(row))

    def test_four_source_direct_ameax_sfdc_owner_and_qq_dedup(self):
        data=sources()
        quote,opp=w.check_source_spreadsheets(data)
        self.assertEqual(quote["Opportunity ID"],w.OPP)
        self.assertEqual(opp["Opportunity Owner"],"Kim Taehoon")

    def test_invalid_opportunity_owner_fail_closed(self):
        data=sources()
        data["SFDC Email Opportunities Raw"][0]["Opportunity Owner"]="Other Sales"
        with self.assertRaisesRegex(SafeError,"SFDC_OWNER"):
            w.check_source_spreadsheets(data)

    def test_qq_already_contains_ameax_no_double_count(self):
        data=sources()
        data["CSS Tax Invoice Extract"][0]["project_id"]=w.AMEA
        with self.assertRaisesRegex(SafeError,"ALREADY_IN_ORIGINAL_QQ"):
            w.check_source_spreadsheets(data)

    def test_second_erp_with_same_project_rejected(self):
        data=sources()
        data["Feishu Latest eTax"].append(dict(
            data["Feishu Latest eTax"][0],
            **{"ERP Invoice Number":"20910000210"}))
        with self.assertRaisesRegex(SafeError,"SAME_PROJECT_BILLING"):
            w.check_source_spreadsheets(data)

    def test_gl_month_and_currency_and_source_not_approximated(self):
        for field,value in (("GL Date","46366"),
                            ("Currency","USD"),
                            ("Source","Projects"),
                            ("Sales","Other Representative")):
            data=sources()
            data["Feishu Latest eTax"][0][field]=value
            with self.assertRaisesRegex(SafeError,"MIRROR_ID_OWNER_AMOUNT_DATE_MISMATCH"):
                w.check_source_spreadsheets(data)

    def test_exact_qq_plus_manual_sum_and_historical_preservation(self):
        w.monthly_kpi_guard([canonical()],False)
        w.monthly_kpi_guard([canonical(),manual()],True)
        with self.assertRaisesRegex(SafeError,"UNEXPECTED_OCT_MONTHLY_SOURCES"):
            w.monthly_kpi_guard([canonical(),manual(),
                {"record_id":"third","fields":{
                    "Source Key":"ERP_ETAX:2026-10:other",
                    "Month":"2026-10"}}],True)

    def test_changing_original_qq_gross_or_count_blocks_overlay(self):
        row=canonical()
        row["fields"]["Invoice Count"]=49
        with self.assertRaisesRegex(SafeError,"QQ_OCT_SOURCE_PARITY_CHANGED"):
            w.monthly_kpi_guard([row],False)

    def test_readonly_plan_never_writes_any_row(self):
        source=sources()
        with mock.patch.dict(os.environ,{
            "FEISHU_BASE_APP_TOKEN":w.EXPECTED_BASE,
            "FEISHU_METRIC_MODE":"plan"}),\
            mock.patch.object(w,"load_source_spreadsheets",return_value=source),\
            mock.patch.object(w,"check_original_certificate"),\
            mock.patch.object(w,"auth",return_value=("token","/base")) ,\
            mock.patch.object(w,"table_catalog",
                return_value={"Monthly Tax Invoice":["table"]}),\
            mock.patch.object(w,"table_path",return_value="/table"),\
            mock.patch.object(w,"list_all",side_effect=lambda path,*a:
                [{"field_name":k,"type":t} for k,t in w.SCHEMAS["Monthly Tax Invoice"]]
                if path.endswith("/fields") else [canonical()]),\
            mock.patch.object(w,"sync_table") as write:
            w.main()
        write.assert_not_called()

    def test_writer_readback_expects_one_manual_and_unchanged_qq(self):
        before=[canonical(),{"record_id":"old","fields":{
            "Source Key":"INVOICE:2026-09","Month":"2026-09",
            "Invoice Count":46}}]
        after=before+[manual()]
        with mock.patch.dict(os.environ,{
            "FEISHU_BASE_APP_TOKEN":w.EXPECTED_BASE,
            "FEISHU_METRIC_MODE":"apply"}),\
            mock.patch.object(w,"load_source_spreadsheets",return_value=sources()),\
            mock.patch.object(w,"check_original_certificate"),\
            mock.patch.object(w,"auth",return_value=("token","/base")),\
            mock.patch.object(w,"table_catalog",
                return_value={"Monthly Tax Invoice":["table"]}),\
            mock.patch.object(w,"table_path",return_value="/table"),\
            mock.patch.object(w,"list_all",side_effect=[
                [{"field_name":k,"type":t} for k,t in w.SCHEMAS["Monthly Tax Invoice"]],
                before,after]),\
            mock.patch.object(w,"sync_table",return_value=(1,0,0)) as write:
            w.main()
        write.assert_called_once()
        self.assertEqual(write.call_args.args[2],[w.manual_record()])


if __name__=="__main__":
    unittest.main()
