import unittest
from diagnose_quality import classify_bar

class QualityBarTests(unittest.TestCase):
    def test_valid(self):
        flags,bp=classify_bar(100,105,95,101)
        self.assertEqual(flags,[]);self.assertEqual(bp,0)
    def test_open_too_high(self):
        flags,bp=classify_bar(110,105,95,101)
        self.assertIn('OPEN_ABOVE_HIGH',flags)
        self.assertGreater(bp,0)
    def test_close_too_low(self):
        flags,bp=classify_bar(100,105,95,94)
        self.assertIn('CLOSE_BELOW_LOW',flags)
        self.assertGreater(bp,0)
    def test_low_greater_than_high(self):
        flags,_=classify_bar(100,90,110,100)
        self.assertIn('LOW_GREATER_THAN_HIGH',flags)
    def test_missing(self):
        self.assertEqual(classify_bar(None,105,95,100)[0],['MISSING_OHLC'])
    def test_slight_violation_quantified(self):
        flags,bp=classify_bar(100.00001,100,99,99.5)
        self.assertIn('OPEN_ABOVE_HIGH',flags)
        self.assertLess(bp,1)

if __name__=='__main__':unittest.main()