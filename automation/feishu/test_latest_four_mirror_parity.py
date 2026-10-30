"""Synthetic, credential-free tests of Feishu mirror and latest source identity."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from latest_four_mirror_parity import MIRRORS,validate_structure,evaluate

def headers():
 return {
 "Payment Outstanding":["Customer Name","ERP Invoice Number","Contact Person","Invoice Type","PO Number","Project Number","CMS Invoice Number","Quotation Number","e-tax Number","Sales","Invoice Date","Due Date","Invoice Amount","Balance","Payment Method","Remark","Expected Date"],
 "Payment Receipt":["Deposit Date","Customer Name","Amount (KRW)","CMS No.","Column 5","Date","CMS No. [2]","Amount","Column 9","Date [2]","Customer Name [2]","Amount [2]","CMS No. [3]"],
 "eTax Invoice":["Comments","Org Name","Source","Type","ERP Invoice Number","CMS Invoice Num","Currency","Exchange Rate","PO Number","Project Number","Quotation Number","Customer Number","Customer Name","Customer VAT","Contact Person","Amount","GL Date","Accounting","Balancing Segment","Profit Segment","Cost Center Segment","Nature Account Segment","Order Number","CRM Order Number","Comments [2]","Sales","Payment Method","Contact Email for e-Tax","Remark","Expected payment date","Paid?\nYes ?","Status","e-Tax issued?","Remark [2]","Payment Link Sent?"],
 "Prepayments":["N/O","Customer Name","ERP Invoice Number","Contact Person","Project Number","Quotation Number","Invoice Date","Invoice Amount","Payment Status","Prepayment Fully Utilised?","Remaining Prepayment (KRW)","CMS Invoice Number","ERP Number","CN Month","Credit Note Issued?","Amount Recognised","Cross-quote/ entity usage?","Payment Method/ Remarks","Sales"],
 }

def selected():
 return {name:{"date":"2026-10-26","sheet_id":"id"+str(i)} for i,name in enumerate(MIRRORS)}

def manifest():
 return [["Source","Source Date","Synced At KST","Source ID","Rows","Schema","Meaning"]]+[
  [name,"2026-10-26","2026-10-30T08:54+09:00","id"+str(i),"123","HEADER_MATCHED","Never paid proof"]
  for i,name in enumerate(MIRRORS)]

class MirrorParityTest(unittest.TestCase):
 def test_actual_four_mirror_panel_positions(self):
  for name,row in headers().items():
   self.assertEqual(validate_structure(name,row),"MIRROR_STRUCTURAL_MATCH",name)
 def test_identical_latest_ids_are_still_raw_unverified(self):
  rows,blocked=evaluate(selected(),manifest(),headers())
  self.assertEqual(blocked,[])
  self.assertEqual(len(rows),4)
  self.assertTrue(all(r["status"]=="MIRROR_MATCH_RAW_UNVERIFIED" for r in rows))
 def test_raw_source_id_or_date_change_blocks_stale_mirror(self):
  s=selected();s["Payment Receipt"]["sheet_id"]="new-tab"
  rows,blocked=evaluate(s,manifest(),headers())
  self.assertIn("Payment Receipt",blocked)
  self.assertIn("MIRROR_SOURCE_ID_NOT_LATEST",rows[1]["checks"])
  s=selected();s["eTax Invoice"]["date"]="2026-10-27"
  _,blocked=evaluate(s,manifest(),headers())
  self.assertIn("eTax Invoice",blocked)
 def test_independent_receipt_panels_not_one_payment_amount(self):
  h=headers();h["Payment Receipt"][7],h["Payment Receipt"][11]=h["Payment Receipt"][11],h["Payment Receipt"][7]
  self.assertEqual(validate_structure("Payment Receipt",h["Payment Receipt"]),
   "CRITICAL_FIELD_MISMATCH_AT_COL_8")
 def test_duplicate_or_missing_canonical_field_blocks(self):
  h=headers()["eTax Invoice"];h[14]=h[15]
  self.assertEqual(validate_structure("eTax Invoice",h),"CANONICAL_DUPLICATE_FIELD")
  self.assertEqual(validate_structure("Payment Receipt",["Deposit Date"]),"CANONICAL_WIDTH_MISSING")
 def test_etax_paid_and_issued_are_independent_fields(self):
  h=headers()["eTax Invoice"];h[32],h[33]=h[33],h[32]
  self.assertEqual(validate_structure("eTax Invoice",h),"CRITICAL_FIELD_MISMATCH_AT_COL_33")
 def test_unverified_mirror_manifest_is_blocked(self):
  m=manifest();m[2][5]="UNVERIFIED"
  rows,blocked=evaluate(selected(),m,headers())
  self.assertIn("Payment Receipt",blocked)
  self.assertIn("MIRROR_MANIFEST_SCHEMA_NOT_MATCHED",rows[1]["checks"])
 def test_duplicate_manifest_record_is_error(self):
  m=manifest();m.append(m[2])
  with self.assertRaisesRegex(RuntimeError,"SOURCE_MANIFEST_DUPLICATE_FORMAT"):
   evaluate(selected(),m,headers())

if __name__=="__main__":unittest.main()
