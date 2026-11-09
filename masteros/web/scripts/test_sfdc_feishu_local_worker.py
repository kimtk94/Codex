import unittest
from sfdc_feishu_local_worker import (price_pair, validate_queue_row, process_row, result_append_url, QHEAD, RHEAD)

ROW=['rec123456789','SFDC-20261109-A001','a'*64,'oppo_quote_pair','PREFLIGHT',
     '006000000000000AAA','a0P000000000000AAA','Korea-New-12-mRNA','Example Univ.',
     'Kim', '12','12.0','2026-11-30','New 12 samples, PO not confirmed.',
     'false','false','false','1700000000']
BUNDLE={'status':'PASS','selectionStatus':'EXACT_ONE','opportunity':{
        'id':ROW[5], 'name':'Korea-Old-42-mRNA','accountName':'Example Univ.',
        'contactName':'Kim','progressDescriptionSource':'old message'},
        'linkedQuotes':[{'id':ROW[6],'opportunityId':ROW[5],'pricingStatus':'VERIFIED_PROCESS_LINES',
          'productCount':1,'sourceVatRateVerified10Pct':True,'cloudLinePresent':True,
          'sampleUnitNetKrw':190000,'cloudUnitNetKrw':35000,'dataSize':12.0}]}
class Tests(unittest.TestCase):
 def test_append_endpoint(self):
    self.assertIn(':append?',result_append_url())
    self.assertIn('valueInputOption=RAW',result_append_url())
 def test_calc(self):
    self.assertEqual(price_pair(BUNDLE,ROW),(2350000,235000,2))
 def test_source_no_cloud(self):
    o={**BUNDLE,'linkedQuotes':[{**BUNDLE['linkedQuotes'][0],'cloudLinePresent':False}]}
    with self.assertRaisesRegex(RuntimeError,'VAT_OR_CLOUD'):
      price_pair(o,ROW)
 def test_wrong_source_quote_id(self):
    a=ROW.copy();a[6]='a0P000000000001AAA'
    with self.assertRaisesRegex(RuntimeError,'EXPLICIT_QUOTE'):
      price_pair(BUNDLE,a)
 def test_changed_gb_blocked(self):
    a=ROW.copy();a[11]='13.0'
    with self.assertRaisesRegex(RuntimeError,'DATA_SIZE_CHANGE'):
      price_pair(BUNDLE,a)
 def test_safety(self):
    self.assertTrue(validate_queue_row(ROW))
    x=ROW.copy();x[4]='SAVE'
    self.assertFalse(validate_queue_row(x))
    x[14:17]=['true','true','true']
    self.assertTrue(validate_queue_row(x))
    result=process_row(x,[],None)
    self.assertEqual(result[0],'BLOCK')
    self.assertEqual(result[1],'PREFLIGHT_PROOF_MISSING')
 def test_no_real_save_without_writer(self):
    x=ROW.copy();x[4]='SAVE';x[14:17]=['true','true','true']
    old=[ROW[0],ROW[1],ROW[2],'PREFLIGHT_PASS','','2350000','235000','','','2026-11-09T12:00:00Z','PREFLIGHT']
    result=process_row(x,[old],None)
    self.assertEqual(result[1],'COMBINED_SFDC_SAVE_NOT_RELEASED')

if __name__=='__main__':unittest.main()
