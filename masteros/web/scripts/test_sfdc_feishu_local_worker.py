import unittest
from unittest import mock
from sfdc_feishu_local_worker import (price_pair, validate_queue_row, process_row, result_append_url, append_result, QHEAD, RHEAD)

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
 def test_append_result_verified_readback(self):
    row=['rec123456789','SFDC-20261109-A001','a'*64,'PREFLIGHT_PASS',
         'CLOUD_UNITS_2','2350000','235000','','','2026-11-11T11:03:00Z','PREFLIGHT']
    session=mock.Mock()
    session.post.return_value.json.return_value={
      'updates':{'updatedRows':1,'updatedRange':"'SFDC Feishu Results'!A2:K2"}}
    session.get.return_value.json.return_value={'values':[row]}
    append_result(session,row)
    self.assertIn(':append?',session.post.call_args.args[0])
    self.assertIn('A2:K2',session.get.call_args.args[0])
 def test_append_result_missing_range_or_wrong_sheet_blocks(self):
    row=['rec123456789','SFDC-20261109-A001','a'*64,'BLOCK',
         'PREFLIGHT_PROOF_MISSING','','','','','2026-11-11T11:03:00Z','PREFLIGHT']
    for updated in ('',"'Other Sheet'!A2:K2",
                    "'SFDC Feishu Results'!A1:K1",
                    "'SFDC Feishu Results'!A2:K3"):
      session=mock.Mock()
      session.post.return_value.json.return_value={
        'updates':{'updatedRows':1,'updatedRange':updated}}
      with self.assertRaisesRegex(RuntimeError,'RESULT_APPEND_RANGE_UNVERIFIED'):
        append_result(session,row)
      session.get.assert_not_called()
 def test_append_result_content_mismatch_blocks(self):
    row=['rec123456789','SFDC-20261109-A001','a'*64,'PREFLIGHT_PASS',
         'CLOUD_UNITS_2','2350000','235000','','','2026-11-11T11:03:00Z','PREFLIGHT']
    session=mock.Mock()
    session.post.return_value.json.return_value={
      'updates':{'updatedRows':1,'updatedRange':"'SFDC Feishu Results'!A5:K5"}}
    other=row.copy();other[2]='b'*64
    session.get.return_value.json.return_value={'values':[other]}
    with self.assertRaisesRegex(RuntimeError,'RESULT_APPEND_READBACK_MISMATCH'):
      append_result(session,row)
 def test_append_result_short_write_blocks(self):
    session=mock.Mock()
    session.post.return_value.json.return_value={
      'updates':{'updatedRows':0,'updatedRange':"'SFDC Feishu Results'!A2:K2"}}
    with self.assertRaisesRegex(RuntimeError,'RESULT_WRITE_SHORT'):
      append_result(session,['']*len(RHEAD))
    session.get.assert_not_called()
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
