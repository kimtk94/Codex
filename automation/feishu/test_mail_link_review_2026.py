#!/usr/bin/env python3
"""No automatic identity link from email domains or quoted body project IDs."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo

import mail_link_review_2026 as review
from mail_identity_2026 import build_index,decorate


NOW=dt.datetime(2026,11,5,22,0,tzinfo=ZoneInfo("Asia/Seoul"))


def fixture():
    return build_index({
        "contacts":[
            {"Email":"person@school.edu","Account Name":"Some University",
             "First Name":"A","Last Name":"Person"},
            {"Email":"other@school.edu","Account Name":"Some University",
             "First Name":"B","Last Name":"Person"},
        ],
        "leads":[],"quotes":[],
        "projects":[{"project_id":"AMEA2026042239","h_project_numbers":"H209SC26065705",
                     "institution":"Some University","customer_name":"A Person"}],
    })


def mail(subject,body="",from_email="unknown@example.net",key="a"*64):
    return {"Mail Key":key,"Subject":subject,"Body Excerpt":body,
            "From":from_email,"To":"sales@novogene.com","Direction":"INBOUND",
            "Received At":"2026-10-25T08:00:00+09:00","In Reply To":""}


class CandidateTests(unittest.TestCase):
    def test_body_only_one_project_requires_review(self):
        idx=fixture()
        x=mail("Request","Previous AMEA2026042239")
        r=decorate(x,idx,NOW)
        self.assertEqual(r["Project ID"],"")
        suggestion=review.suggestion(x,r,idx,review.domains_by_account(idx))
        self.assertEqual(suggestion["Candidate Basis"],"BODY_PROJECT_UNIQUE")
        self.assertEqual(suggestion["Candidate Project"],"AMEA2026042239")
        self.assertEqual(suggestion["Identity Status"],"UNMATCHED")

    def test_domain_unique_is_candidate_not_verified(self):
        idx=fixture()
        x=mail("New inquiry",from_email="newperson@school.edu")
        relation=decorate(x,idx,NOW)
        self.assertEqual(relation["Account"],"")
        candidate=review.suggestion(x,relation,idx,review.domains_by_account(idx))
        self.assertEqual(candidate["Candidate Account"],"Some University")
        self.assertEqual(candidate["Candidate Basis"],"DOMAIN_ACCOUNT_UNIQUE")
        self.assertEqual(relation["Relationship Status"],"UNMATCHED")

    def test_generic_email_domain_not_candidate(self):
        idx=fixture()
        x=mail("New inquiry",from_email="somebody@gmail.com")
        relation=decorate(x,idx,NOW)
        self.assertIsNone(review.suggestion(x,relation,idx,review.domains_by_account(idx)))

    def test_exactly_linked_mail_never_enters_review_queue(self):
        idx=fixture()
        x=mail("AMEA2026042239",from_email="person@school.edu")
        relation=decorate(x,idx,NOW)
        self.assertEqual(relation["Relationship Status"],"LINKED")
        self.assertIsNone(review.suggestion(x,relation,idx,review.domains_by_account(idx)))

    def test_conflicting_domain_project_marks_conflict(self):
        idx=fixture()
        x=mail("Hello","Earlier AMEA2026042239",from_email="new@school.edu")
        relation=decorate(x,idx,NOW)
        self.assertEqual(relation["Relationship Status"],"UNMATCHED")
        candidate=review.suggestion(x,relation,idx,review.domains_by_account(idx))
        self.assertEqual(candidate["Candidate Project"],"AMEA2026042239")
        self.assertEqual(candidate["Candidate Account"],"Some University")
        self.assertEqual(candidate["Candidate Basis"],"BODY_PROJECT_UNIQUE")

    def test_decision_not_overwritten_by_sync(self):
        original={"Mail Key":"k","Candidate Basis":"DOMAIN_ACCOUNT_UNIQUE",
                  "Review Status":"REJECTED","Review Note":"manual"}
        updated={"Mail Key":"k","Candidate Basis":"DOMAIN_ACCOUNT_UNIQUE"}
        self.assertTrue(review.same(original,updated))
        self.assertNotIn("Review Status",updated)
        self.assertNotIn("Review Note",updated)


if __name__=="__main__":
    unittest.main()
