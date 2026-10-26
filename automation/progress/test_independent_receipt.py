import unittest
import hashlib
from independent_receipt import verify_receipt
from tracker import SHEET_ID
def fixture():
    run={"id":123,"event":"schedule","conclusion":"success","head_sha":"abc"}
    receipt={"run_id":"123","commit_sha":"abc","state":"VERIFIED_WRITE_RECEIPT","spreadsheet_id":SHEET_ID,
       "target_tab":"Automation Master Progress","verified_cells":["F52"],
       "cell_sha256":{"F52":hashlib.sha256(b"evidence").hexdigest()}}
    return run,receipt
class IndependentReceiptTests(unittest.TestCase):
    def test_valid(self):
        a,b=fixture()
        self.assertEqual("OBSERVED",verify_receipt(a,b,{"F52":"evidence"})[0])
    def test_pull_request_rejected(self):
        a,b=fixture();a["event"]="pull_request"
        self.assertEqual("NOT_VERIFIED",verify_receipt(a,b,{"F52":"evidence"})[0])
    def test_run_mismatch_rejected(self):
        a,b=fixture();b["run_id"]="456"
        self.assertEqual("NOT_VERIFIED",verify_receipt(a,b,{"F52":"evidence"})[0])
    def test_changed_sheet_rejected(self):
        a,b=fixture()
        self.assertEqual("NOT_VERIFIED",verify_receipt(a,b,{"F52":"changed"})[0])
if __name__=="__main__":unittest.main()
