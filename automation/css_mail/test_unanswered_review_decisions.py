#!/usr/bin/env python3
"""Offline opt-in skipping/routing tests; no Google Sheets or mail credentials."""
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import unanswered_review_decisions as d

ME="owner@novogene.com"
CUSTOMER="client@lab.edu"
PERSON="colleague@novogene.com"

def candidate(key="INBOX|V|100", recipient=PERSON, cc=ME, sender=CUSTOMER):
    result=["P0",3,"2026-11-10 14:20",sender,"mRNA quote","","NO_REPLY_EVIDENCE",
            "회신 필요","CANDIDATE_NOT_CONFIRMED","<thread@lab.edu>","inbox:100",
            "",recipient,cc,key,"2026-11-10T08:00:00+00:00",
            "2026-11-10T09:00:00+00:00","STAGING_METADATA_PARTIAL_HISTORY",
            "BI Mail Review & Exclusions"]
    assert len(result)==19
    return result

def edited(row, action, target="", note=""):
    return row+[d.receipt_role(row,ME),action,target,note,"REVIEW"]

class RoutingRules(unittest.TestCase):
    def test_cc_role_cannot_be_based_on_union(self):
        self.assertEqual(d.receipt_role(candidate(), ME),"CC_ONLY")
        self.assertEqual(d.receipt_role(candidate(recipient=ME),ME),"TO")
        self.assertFalse(d.cc_only(candidate(recipient=ME,cc=ME),ME))

    def test_skip_mail_single_key(self):
        a=candidate()
        rows=[d.DECISION_HEAD]; rules=[d.RULE_HEAD]
        # A review queue is editable only when its complete header is intact.
        header=[str(x) for x in a]
        header[14]="Canonical Ingest Key"
        queue=[header+d.APPEND_HEAD,edited(a,"SKIP_MAIL",note="Not my inquiry")]
        todo, rtodo=d.plan(queue,[a],rows,rules,ME)
        self.assertEqual(len(todo),1)
        self.assertEqual(rtodo,[])
        visible, stats=d.filtered_queue([a],rows+todo,rules,ME)
        self.assertEqual(visible,[])
        self.assertEqual(stats["SKIPPED_MAIL"],1)

    def test_cc_to_rule_does_not_hide_direct_to(self):
        row=candidate()
        other=candidate(key="INBOX|V|101",recipient=ME,cc=PERSON)
        rules=[d.RULE_HEAD,["TRUE","TO_ADDRESS",PERSON,
                           "OWNER_CC_ONLY","SKIP","","",""]]
        visible,stats=d.filtered_queue([row,other],[d.DECISION_HEAD],rules,ME)
        self.assertEqual(len(visible),1)
        self.assertEqual(visible[0][14],other[14])
        self.assertEqual(stats["SKIPPED_CC_TO_RULE"],1)
        self.assertEqual(stats["VISIBLE_TO"],1)

    def test_cc_sender_rule_not_global(self):
        rules=[d.RULE_HEAD,["TRUE","SENDER_ADDRESS",CUSTOMER,
                           "OWNER_CC_ONLY","SKIP","","",""]]
        visible,stats=d.filtered_queue([candidate(),candidate(key="k2",recipient=ME,cc="")],
                                        [d.DECISION_HEAD],rules,ME)
        self.assertEqual(len(visible),1)
        self.assertEqual(stats["SKIPPED_CC_SENDER_RULE"],1)

    def test_disabled_rule_no_longer_skips(self):
        rules=[d.RULE_HEAD,["FALSE","TO_ADDRESS",PERSON,
                           "OWNER_CC_ONLY","SKIP","","",""]]
        visible,_=d.filtered_queue([candidate()],[d.DECISION_HEAD],rules,ME)
        self.assertEqual(len(visible),1)

    def test_wrong_to_address_rejected(self):
        row=candidate()
        queue=[["h"]*14+["Canonical Ingest Key"]+[""]*4+d.APPEND_HEAD,
               edited(row,"SKIP_CC_TO",target="absent@novogene.com")]
        with self.assertRaises(ValueError):
            d.plan(queue,[row],[d.DECISION_HEAD],[d.RULE_HEAD],ME)

    def test_cc_rule_rejected_on_direct_message(self):
        row=candidate(recipient=ME,cc="")
        queue=[["h"]*14+["Canonical Ingest Key"]+[""]*4+d.APPEND_HEAD,
               edited(row,"SKIP_CC_TO",target=ME)]
        with self.assertRaises(ValueError):
            d.plan(queue,[row],[d.DECISION_HEAD],[d.RULE_HEAD],ME)

    def test_stale_row_rejected(self):
        row=candidate()
        queue=[["h"]*14+["Canonical Ingest Key"]+[""]*4+d.APPEND_HEAD,
               edited(row,"SKIP_MAIL")]
        with self.assertRaises(RuntimeError):
            d.plan(queue,[],[d.DECISION_HEAD],[d.RULE_HEAD],ME)

    def test_stale_recipient_reference_rejected(self):
        row=candidate()
        queue=[["h"]*14+["Canonical Ingest Key"]+[""]*4+d.APPEND_HEAD,
               edited(row,"SKIP_MAIL")]
        with self.assertRaises(RuntimeError):
            d.plan(queue,[candidate(recipient="another@novogene.com")],
                   [d.DECISION_HEAD],[d.RULE_HEAD],ME)

    def test_cc_sender_autofilled_exact_address(self):
        row=candidate()
        queue=[["h"]*14+["Canonical Ingest Key"]+[""]*4+d.APPEND_HEAD,
               edited(row,"SKIP_CC_SENDER")]
        mail,rules=d.plan(queue,[row],[d.DECISION_HEAD],[d.RULE_HEAD],ME)
        self.assertEqual(mail,[])
        self.assertEqual(rules[0][1:5],
                         ["SENDER_ADDRESS",CUSTOMER,"OWNER_CC_ONLY","SKIP"])

    def test_cc_exact_rule_no_domain_match(self):
        rules=[d.RULE_HEAD,["TRUE","SENDER_ADDRESS","different@lab.edu",
                           "OWNER_CC_ONLY","SKIP","","",""]]
        visible,_=d.filtered_queue([candidate()],[d.DECISION_HEAD],rules,ME)
        self.assertEqual(len(visible),1)

if __name__=="__main__":
    unittest.main()
