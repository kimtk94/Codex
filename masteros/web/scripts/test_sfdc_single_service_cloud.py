import unittest
from sfdc_record_catalog import parse_process_price_rows

HEADER=["","Pack No.","Process Name","Process Type","Sample Number","Data Size","Data Unit","Unit Price","Total Price"]
def row(process,typ,qty,rate,size=12):
    return ["", "Pack-1",process,typ,str(qty),str(size),"Gb",str(rate),str(qty*rate)]
def source(samples,cloud_qty):
    return [HEADER,row("Library preparation","mRNA library preparation",samples,190000),
            row("Data release","AliCloud",cloud_qty,35000)]
class CloudProcessTest(unittest.TestCase):
    def test_real_42_samples_cloud_504gb(self):
        p=parse_process_price_rows(source(42,6),42,12,8190000)
        self.assertEqual(p["pricingStatus"],"VERIFIED_PROCESS_LINES")
        self.assertEqual((p["sampleUnitNetKrw"],p["cloudUnitNetKrw"],p["sourceCloudUnits"]),(190000,35000,6))
        self.assertTrue(p["cloudLinePresent"])
    def test_12_samples_144gb_cloud_two(self):
        p=parse_process_price_rows(source(12,2),12,12,2350000)
        self.assertEqual(p["sourceCloudUnits"],2)
    def test_exact_100gb_cloud_one(self):
        self.assertEqual(parse_process_price_rows(source(10,1),10,10,1935000)["sourceCloudUnits"],1)
    def test_150gb_cloud_two(self):
        self.assertEqual(parse_process_price_rows(source(10,2),10,15,1970000)["sourceCloudUnits"],2)
    def test_mismatch_cloud_qty_blocked(self):
        with self.assertRaisesRegex(ValueError,"SOURCE_CLOUD_QTY_INCORRECT"):
            parse_process_price_rows(source(12,1),12,12,2315000)
    def test_wrong_total_blocked(self):
        with self.assertRaisesRegex(ValueError,"PROCESS_NET_SUM_MISMATCH"):
            parse_process_price_rows(source(12,2),12,12,2340000)
    def test_duplicate_cloud_blocked(self):
        rows=source(12,2)+[row("Data release","AliCloud premium",2,35000)]
        with self.assertRaisesRegex(ValueError,"MULTIPLE_CLOUD"):
            parse_process_price_rows(rows,12,12,2420000)

if __name__=="__main__":
    unittest.main()
