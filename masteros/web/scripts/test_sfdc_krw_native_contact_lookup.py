"""Synthetic-only native contact result tests; never connect to Salesforce."""
import datetime as dt
import unittest
from sfdc_krw_native_contact_lookup import (
    validate_query,select_candidates,process,VERSION,SOURCE
)

NOW=dt.datetime(2026,11,16,13,0,tzinfo=dt.timezone.utc)
def contact(c="003000000000AAA",a="001000000000AAA",name="김지훈"):
    return {
      "korean_name":name,"institution_name":"합성대학교","account_name":"합성대학교",
      "account_id":a,"contact_id":c,
      "linked_opportunity_ids":["006000000000AAA"],
      "source_qid":"QID-2026-11-16-414586",
      "quote_record_id":"a0P000000000AAA",
      "amea_id":"AMEA2026111604",
      "email":"synthetic@example.org",
      "sfdc_quote_contact_oppo_verified":True,
      "salesforce_write_performed":False,
    }
def doc(*contacts):
    return {
        "version":VERSION,"source":SOURCE,"salesforce_write_performed":False,
        "generated_at":"2026-11-16T12:00:00+00:00",
        "contacts":list(contacts)
    }
class NativeKrwContactTests(unittest.TestCase):
    def test_name_validation_and_native_account_filter(self):
        self.assertEqual(validate_query({"query":"김지훈","limit":10})[0],"김지훈")
        for bad in [
            {"query":"KimJiHoon","limit":10},
            {"query":"김지훈","limit":20},
            {"query":"김지훈","limit":2,"accountId":"CP100"},
            {"query":"김지훈","limit":2,"save":True},
        ]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_query(bad)

    def test_exact_korean_name_only_and_other_institution_never_conflated(self):
        rows=doc(contact(),contact(c="003000000000AAB",a="001000000000AAB"))
        got=select_candidates(rows,{"query":"김지훈","limit":10},NOW)
        self.assertEqual(len(got),2)
        account=select_candidates(rows,{"query":"김지훈","limit":10,
                                         "accountId":"001000000000AAA"},NOW)
        self.assertEqual(len(account),1)
        self.assertEqual(len(select_candidates(rows,{"query":"이태백","limit":10},NOW)),0)

    def test_stale_index_unverified_id_and_truncated_scope_block(self):
        good=doc(contact())
        with self.assertRaisesRegex(ValueError,"CONTACT_INDEX_STALE"):
            select_candidates({**good,"generated_at":"2026-11-10T00:00:00+00:00"},
                              {"query":"김지훈","limit":10},NOW)
        with self.assertRaisesRegex(ValueError,"CONTACT_ROW_UNVERIFIED"):
            select_candidates(doc({**contact(),"contact_id":"CP123456789012"}),
                              {"query":"김지훈","limit":10},NOW)
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_CONTACT_MATCH_SCOPE"):
            select_candidates(doc(contact(),contact(c="003000000000AAB",a="001000000000AAB")),
                              {"query":"김지훈","limit":1},NOW)

    def test_no_silent_homonym_loss_when_one_live_recheck_fails(self):
        two=doc(contact(),contact(c="003000000000AAB",a="001000000000AAB"))
        # process calls the clock internally; substitute a fresh timestamp here
        two["generated_at"]=dt.datetime.now(dt.timezone.utc).isoformat()
        bad=process({"query":"김지훈","limit":10},two,
                    lambda row: {"contact_id":row["contact_id"]} if
                       row["contact_id"]=="003000000000AAA" else None)
        self.assertEqual(bad["status"],"BLOCK")
        self.assertEqual(bad["candidates"],[])
        self.assertEqual(bad["unresolved_matches"],1)
        self.assertIs(bad["salesforce_write"],False)

    def test_empty_match_stays_scope_limited_not_global_not_found(self):
        one=doc(contact());one["generated_at"]=dt.datetime.now(dt.timezone.utc).isoformat()
        reply=process({"query":"이태백","limit":10},one,None)
        self.assertEqual(reply["status"],"PASS")
        self.assertEqual(reply["candidates"],[])
        self.assertEqual(reply["coverage"],"VERIFIED_2026_KRW_QUOTE_CONTACTS_ONLY")

if __name__=="__main__":
    unittest.main()
