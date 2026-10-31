import unittest
import pandas as pd
from crosscheck_fx_sources import validate_bar, label_audit, flatten_yahoo

class FXCrosscheckContractTests(unittest.TestCase):
    def test_bad_ohlc(self):
        valid,bps=validate_bar({'open':101,'high':100,'low':99,'close':100})
        self.assertFalse(valid);self.assertEqual(bps,100)
        self.assertTrue(validate_bar({'open':100,'high':102,'low':99,'close':100})[0])
    def test_no_auto_replace_label(self):
        self.assertEqual(label_audit(False,False,True,True),'YAHOO_REPAIR_FLAG_CANDIDATE')
        self.assertEqual(label_audit(False,False,False,True),'YAHOO_UNREPAIRED_AND_REPAIRED_INVALID')
        self.assertEqual(label_audit(False,True,True,True),'SNAPSHOT_OR_UPSTREAM_VERSION_DRIFT')
    def test_flatten_yahoo(self):
        i=pd.date_range('2024-01-01',periods=3,freq='D')
        df=pd.DataFrame({'Open':[100,101,102], 'High':[101,102,103], 'Low':[99,100,101], 'Close':[100,102,103]},index=i)
        out=flatten_yahoo(df,'KRW=X')
        self.assertEqual(out.loc['2024-01-01','open'],100)
    def test_flatten_multi_yahoo(self):
        i=pd.date_range('2024-01-01',periods=2)
        cols=pd.MultiIndex.from_tuples([('Open','KRW=X'),('High','KRW=X'),('Low','KRW=X'),('Close','KRW=X')])
        df=pd.DataFrame([[100,102,99,101],[102,103,101,102]],columns=cols,index=i)
        out=flatten_yahoo(df,'KRW=X')
        self.assertEqual(out.loc['2024-01-01','close'],101)
if __name__=='__main__':unittest.main()