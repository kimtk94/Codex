"""Synthetic-only verification of native SFDC 2026 KRW Process source bundles."""
import copy
import unittest
from quote_native_save_source_audit import audit_source_bundle


def fixtures():
    queue={
      "canonical":{
        "reference":{"sourceQuoteId":"a0P000000000001","opportunityId":"006000000000001"},
        "proposed":{"name":"Korea-Synthetic-PMP-4-5Gb",
          "products":[{
            "id":"QD-000001","samples":"4","sampleUnitKrw":"57500",
            "processNames":["Data release","Sequencing by data amount",
              "Library QC","Analysis by sample"],
            "processIds":["Process-2020-04-29-00032","Process-2020-04-29-00031",
              "Process-2020-04-30-00044","Process-2020-04-29-00034"],
            "fixedProcessLines":[{"processName":"Data release",
              "processId":"Process-2020-04-29-00032","netKrw":30000}]}]
        }
      }
    }
    costs=[
      ("Library QC",4,20000,80000,"Library QC","Package1"),
      ("Sequencing by data amount",4,37500,150000,"Sequencing","Package1"),
      ("Analysis by sample",4,0,0,"Analysis","Package1"),
      ("Data release",1,30000,30000,"AliCloud",None)
    ]
    processes=[{
      "name":name,
      "native_id":"a0L00000000000"+str(i),
      "process_master_id":"a0E00000000000"+str(i),
      "native_quotation_product_id":"a0N000000000001",
      "quantity":qty,"unit_price_krw":rate,"net_krw":total,
      "process_type":typ,"pack":pack,"currency":"KRW",
      "data_size":5 if typ in ("Sequencing","Analysis") else None,
      "data_unit":"G raw data" if typ in ("Sequencing","Analysis") else None
    } for i,(name,qty,rate,total,typ,pack) in enumerate(costs,1)]
    bundle={
      "source_quotation_id":"a0P000000000001",
      "source_opportunity_id":"006000000000001",
      "new_opportunity_name":"Korea-Synthetic-PMP-4-5Gb",
      "quote_net_krw":"260000","quote_gross_krw":"286000",
      "product":{"source_reference_product_id":"QD-000001",
        "native_product_id":"01t000000000001",
        "native_quotation_product_id":"a0N000000000001"},
      "processes":processes
    }
    terms={"proposed_exact_name":"Korea-Synthetic-PMP-4-5Gb",
      "approved_terms":{"net_krw":"260000","gross_krw":"286000",
        "alicloud":"EXCLUDE","price_approved_by_operator":True}}
    return queue,bundle,terms


class NativeSourceAuditTests(unittest.TestCase):
    def test_readback_identifies_alicloud_policy_ambiguity_not_save(self):
        q,b,t=fixtures()
        result=audit_source_bundle(q,b,t)
        self.assertEqual(result["status"],"HOLD_NATIVE_QUOTE_SOURCE")
        self.assertEqual(result["reason_codes"],
          ["ALICLOUD_EXCLUDED_BUT_SOURCE_HAS_ALICLOUD_TYPED_PROCESS"])
        self.assertEqual(len(result["source_processes"]),4)
        self.assertTrue(result["native_source_verified"])
        self.assertTrue(result["native_source_snapshot_complete"])
        self.assertFalse(result["new_quotation_price_approval"])
        self.assertFalse(result["save_permitted"])
        self.assertEqual(result["crm_writes"],0)

    def test_explicit_operator_inclusion_resolves_only_source_audit_not_save(self):
        q,b,t=fixtures()
        t["approved_terms"]["alicloud"]="INCLUDE_EXISTING_DATA_RELEASE_ONLY"
        result=audit_source_bundle(q,b,t)
        self.assertEqual(result["status"],"NATIVE_SOURCE_LINES_VERIFIED_NOT_SAVE_APPROVED")
        self.assertTrue(result["native_source_verified"])
        self.assertEqual(result["source_processes"][0]["native_process_master_id"],
            "a0E000000000001")
        self.assertFalse(result["save_permitted"])

    def test_source_quotation_product_and_process_ids_cannot_be_swapped(self):
        q,b,t=fixtures()
        t["approved_terms"]["alicloud"]="INCLUDE_EXISTING_DATA_RELEASE_ONLY"
        b["processes"][0]["native_quotation_product_id"]="a0N000000000002"
        self.assertIn("NATIVE_PROCESS_MASTER_ID_OR_PARENT_UNVERIFIED",
            audit_source_bundle(q,b,t)["reason_codes"])

    def test_price_and_sample_count_must_reconcile_exactly(self):
        q,b,t=fixtures()
        t["approved_terms"]["alicloud"]="INCLUDE_EXISTING_DATA_RELEASE_ONLY"
        b["processes"][1]["quantity"]=5
        self.assertIn("NATIVE_PROCESS_QUANTITY_RATE_TOTAL_INVALID",
          audit_source_bundle(q,b,t)["reason_codes"])
        b["processes"][1]["quantity"]=4
        b["quote_net_krw"]="230000"
        self.assertIn("NEW_AND_SOURCE_KRW_TOTALS_MISMATCH",
          audit_source_bundle(q,b,t)["reason_codes"])

    def test_report_short_code_not_mistaken_for_native_master_id(self):
        q,b,t=fixtures()
        t["approved_terms"]["alicloud"]="INCLUDE_EXISTING_DATA_RELEASE_ONLY"
        b["processes"][0]["process_master_id"]="PR0010"
        self.assertIn("NATIVE_PROCESS_MASTER_ID_OR_PARENT_UNVERIFIED",
            audit_source_bundle(q,b,t)["reason_codes"])

    def test_preserves_exact_name_even_when_source_names_repeat(self):
        q,b,t=fixtures()
        t["approved_terms"]["alicloud"]="INCLUDE_EXISTING_DATA_RELEASE_ONLY"
        t["proposed_exact_name"]+=" -02"
        self.assertIn("NAME_MUST_BE_EXACTLY_PRESERVED",
            audit_source_bundle(q,b,t)["reason_codes"])


if __name__=="__main__":unittest.main()
