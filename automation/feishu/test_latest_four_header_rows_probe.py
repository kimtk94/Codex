"""Header-position diagnostics: use synthetic values only, never real customer data."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from latest_four_header_rows_probe import analyze_rows,verify_mirror_identity,kind

class HeaderProbeTests(unittest.TestCase):
 def test_null_sparse_multirow_receipt_is_not_implicitly_accepted(self):
  mirror=["Deposit Date","Customer Name","Amount (KRW)","CMS No.","Column 5","Date",
          "CMS No. [2]","Amount","Column 9","Date [2]","Customer Name [2]","Amount [2]","CMS No. [3]"]
  rows=[["Deposit Date",None,None,None,None,"Date"],[None,"Customer Name",None,"CMS No."],
        [None,None,"Amount (KRW)",None,None,None,"CMS No. [2]","Amount"]]
  r=analyze_rows(rows,mirror,13,[1,2,3,4,6,7,8,10,11,12,13])
  self.assertEqual(r["raw_header_status"],"STRUCTURE_UNRESOLVED")
  self.assertEqual(r["required_position_matches_across_sample"],[1,2,3,4,6,7,8])
  self.assertEqual(r["missing_required_positions"],[10,11,12,13])
  self.assertFalse(r["certified"])
  self.assertEqual(r["row_summaries"][0]["types"]["NULL"],50)
 def test_full_row_is_only_candidate_not_raw_acceptance(self):
  h=["Column "+str(i) for i in range(1,14)]
  r=analyze_rows([h],h,13,[1,2,3,4,6,7,8,10,11,12,13])
  self.assertEqual(r["raw_header_status"],"CANDIDATE_ONLY_REQUIRE_RAW_SCHEMA_AUDIT")
  self.assertFalse(r["certified"])
 def test_eTax_nontext_objects_only_expose_counts(self):
  h=["H"+str(i) for i in range(1,36)]
  rows=[[{"secret":"DO_NOT_LOG"},None,4,True,"H5"]]
  r=analyze_rows(rows,h,35,[1,5,10,16,26,31,32,33])
  self.assertEqual(r["row_summaries"][0]["types"]["OBJECT"],1)
  self.assertEqual(r["row_summaries"][0]["types"]["NUMBER"],1)
  self.assertNotIn("DO_NOT_LOG",str(r))
  self.assertIn(33,r["missing_required_positions"])
 def test_wrong_mirror_sheet_id_or_date_is_blocked(self):
  selected={"Payment Receipt":{"sheet_id":"latest","date":"2026-10-30"}}
  mirror={"Payment Receipt":{"id":"previous","date":"2026-10-30","schema":"HEADER_MATCHED"}}
  with self.assertRaisesRegex(RuntimeError,"SOURCE_ID_OR_DATE_MISMATCH"):
   verify_mirror_identity("Payment Receipt",selected,mirror)
  mirror["Payment Receipt"]["id"]="latest"
  self.assertEqual(verify_mirror_identity("Payment Receipt",selected,mirror),"latest")
  mirror["Payment Receipt"]["schema"]="UNVERIFIED"
  with self.assertRaisesRegex(RuntimeError,"MIRROR_SCHEMA_UNVERIFIED"):
   verify_mirror_identity("Payment Receipt",selected,mirror)
 def test_risky_cells_and_invalid_width_are_rejected(self):
  with self.assertRaisesRegex(ValueError,"ROW_TOO_WIDE"):
   analyze_rows([["x"]*53],["x"]*13,13)
  with self.assertRaisesRegex(ValueError,"MIRROR_HEADER_WIDTH_INVALID"):
   analyze_rows([["A"]],["A"],13)
 def test_only_types_positions_and_coverage_leave_the_analysis(self):
  r=analyze_rows([["PRIVATE_ACCOUNT_VALUE","PRIVATE_NAME"]],["X","Y"],2,[1,2])
  s=str(r)
  self.assertNotIn("PRIVATE_ACCOUNT_VALUE",s)
  self.assertNotIn("PRIVATE_NAME",s)
  self.assertEqual(r["missing_required_positions"],[1,2])
 def test_boolean_has_separate_type_from_integer(self):
  self.assertEqual(kind(True),"BOOLEAN")
  self.assertEqual(kind(42),"NUMBER")

if __name__=="__main__":unittest.main()
