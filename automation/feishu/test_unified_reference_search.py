import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import unified_reference_search as u
import global_relationship_coverage as g
import global_mail_relationship_coverage as m

P="AMEA2026000001"
Q="AMEA2026000002"
H="H209SC26000001"
X="X209SC26000001-Z01"
S="SAM20260000001"
CMS="209126000001"
QUOTE="a0PAbc123456789"
QID="QID-2026-000001"
OPP="Opp-2026-000001"
TUPLE="INBOX|123|456"
KEY=hashlib.sha256(TUPLE.encode()).hexdigest()

def sources():
    return {k:[] for k in g.SOURCES}

def tables():
    return {k:[] for k in m.TABLE_FIELDS}

def canonical(**kw):
    return {"canonical_key":"imap:"+TUPLE,"source_table":"CSS Git Ingest",
            "imap_folder":"INBOX","uidvalidity":"123","imap_uid":"456",
            "message_id":"<synthetic@example.invalid>","amea_numbers":P,
            "h_project_numbers":H,"sam_numbers":S,"subject":"","invoice_numbers":"",**kw}

class SearchTests(unittest.TestCase):
    def test_quote_checksum_and_case(self):
        q=u.sf18(QUOTE,"QUOTE_OBJECT")
        self.assertEqual(len(q),18)
        self.assertEqual(u.queries("QUOTE",QUOTE),{("QUOTE_OBJECT",q)})
        self.assertEqual(u.queries("QUOTE",q),{("QUOTE_OBJECT",q)})
        with self.assertRaisesRegex(u.SearchError,"INVALID_TYPED_QUERY"):
            u.queries("QUOTE",q[:-1]+("B" if q[-1]=="A" else "A"))

    def test_literal_mixed_case_opportunity(self):
        self.assertEqual(u.queries("OPP_REF",OPP),{("OPP_REF",OPP)})
        self.assertNotEqual(u.queries("OPP_REF",OPP),u.queries("OPP_REF",OPP.upper()))

    def test_nonmail_query_and_explicit_edges_only(self):
        s=sources()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":S}]
        s["CSS Project Timeline"]=[{"project_id":Q,"h_project_numbers":H,"sam_numbers":S}]
        idx=u.ReferenceIndex()
        u.add_nonmail(idx,s)
        out=idx.search("AMEA",P)
        self.assertEqual(out["matched_source_rows"],1)
        self.assertEqual(out["direct_reference_edges_total"],2)
        self.assertEqual(idx.search("H",H)["matched_source_rows"],2)
        self.assertNotIn(Q,json.dumps(out))
        self.assertEqual(out["business_writes"],0)

    def test_no_cross_join_or_partial_edge(self):
        idx=u.ReferenceIndex()
        idx.add("synthetic",1,{"a":{("AMEA",P),("AMEA",Q)},"h":{("H",H)}},(("a","h"),))
        idx.add("synthetic",2,{"a":{("AMEA",P)},"h":{("H",H)}},(("a","h"),),review={"h"})
        out=idx.search("AMEA",P)
        self.assertEqual(out["matched_source_rows"],2)
        self.assertEqual(out["direct_reference_edges_total"],0)

    def test_x_namespaces_and_suffix_do_not_merge(self):
        idx=u.ReferenceIndex()
        idx.add("lifecycle",1,{"x":{("X_PROJECT",X)}})
        idx.add("finance",1,{"x":{("X_REPORTED",X)}})
        idx.add("finance",2,{"x":{("X_REPORTED",X.replace("-Z01",""))}})
        self.assertEqual(idx.search("X",X)["matched_source_rows"],2)
        self.assertEqual(idx.search("X_PROJECT",X)["matched_source_rows"],1)
        self.assertEqual(idx.search("X",X.replace("-Z01","-Z02"))["matched_source_rows"],0)

    def test_invoice_domains_separate(self):
        idx=u.ReferenceIndex()
        idx.add("finance",1,{"cms":{("CMS",CMS)}})
        idx.add("registry",1,{"doc":{(u.DOC_KIND,CMS)}})
        self.assertEqual(idx.search("CMS",CMS)["source_row_counts"],{"finance":1})
        self.assertEqual(idx.search(u.DOC_KIND,CMS)["source_row_counts"],{"registry":1})

    def test_mail_tuple_lookup_separate_crm_and_no_inferred_edges(self):
        idx=u.ReferenceIndex()
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"AMEA":P+";"+Q,"H Project":H}]
        t[m.CRM]=[{"Mail Key":KEY,"AMEA":P}]
        u.add_mail(idx,[canonical()],t)
        out=idx.search("QQ_MAIL_KEY",KEY)
        self.assertEqual(out["matched_source_rows"],2)
        self.assertEqual(out["source_row_counts"],{"Canonical Mail Ledger":1,m.QQ:1})
        self.assertEqual(idx.search("CRM_MAIL_KEY",KEY)["matched_source_rows"],1)
        self.assertEqual(idx.search("AMEA",P)["direct_reference_edges_total"],0)

    def test_mail_invoice_literal_only_and_bare_number_excluded(self):
        idx=u.ReferenceIndex()
        u.add_mail(idx,[canonical(subject="CMS "+CMS+" Invoice 209126000002 phone 209126000003")],tables())
        self.assertEqual(idx.search("EXPLICIT_CMS_NUMBER",CMS)["matched_source_rows"],1)
        self.assertEqual(idx.search("CMS",CMS)["matched_source_rows"],0)
        self.assertEqual(idx.search("INVOICE_LABELLED_NUMBER","209126000002")["matched_source_rows"],1)
        self.assertEqual(idx.search("INVOICE_LABELLED_NUMBER","209126000003")["matched_source_rows"],0)

    def test_pagination_exact_counts_and_no_truncation_claim(self):
        idx=u.ReferenceIndex()
        for i in range(3):
            idx.add("synthetic",i,{"a":{("AMEA",P)}})
        out=idx.search("AMEA",P,offset=1,limit=1)
        self.assertEqual(out["matched_source_rows"],3)
        self.assertEqual(len(out["records"]),1)
        self.assertEqual(out["records_remaining"],1)
        with self.assertRaisesRegex(u.SearchError,"PAGE_BOUND"):
            idx.search("AMEA",P,limit=5001)

    def test_local_only_and_exclusive_destination(self):
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"true"}):
            with self.assertRaisesRegex(u.SearchError,"LOCAL_ONLY"):
                u.private_target("unused")
        with patch.dict(os.environ,{},clear=True),tempfile.TemporaryDirectory() as d:
            target=Path(d)/"private.json"
            self.assertEqual(u.private_target(str(target)),target.resolve())
            target.touch()
            with self.assertRaisesRegex(u.SearchError,"NEW_LOCAL_FILE_REQUIRED"):
                u.private_target(str(target))
            with self.assertRaisesRegex(u.SearchError,"ABSOLUTE_OUTPUT_REQUIRED"):
                u.private_target("relative.json")

if __name__=="__main__":
    unittest.main()
