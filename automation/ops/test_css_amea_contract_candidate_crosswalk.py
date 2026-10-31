"""Offline regression for AMEA-keyed Feishu contract candidate crosswalk."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from css_amea_contract_candidate_crosswalk import assess,xbase

NOW=dt.datetime(2026,10,31,20,0,tzinfo=ZoneInfo("Asia/Seoul"))
WH=["AMEA Project ID","Project / Institution / Service","Forecast Month","Estimated Completion",
    "Quote KRW","Quote K USD","Matched Invoice Count","Forecast Status","TAT Basis",
    "Source","Review Status","","H Contract","X Sub-project","Stage"]
OH=["Feishu Record ID","Contract Number","Sub-Project Number","Nation","Supplementary Contract",
    "Lab","Staging Number","Staging Name","Remaining Lead Time-Calendar Days",
    "Planning Settled Month","Normal/Ideal Settlement Prediction",
    "Planning Settled Amount Excluding Tax in USD",
    "Planning Settled Amount in Contract Currency","TS","Sales","remark","TS/AM update",
    "Contract Name","Project Status","Progression Details","Special Progression Details",
    "UnknownName","Sub-Project PO Amount","UnknownName_1","PC","SourceID"]
FH=["Customer Name","ERP Invoice Number","Contact Person","Invoice Type","PO Number",
    "Project Number","CMS Invoice Number","Quotation Number","e-tax Number",
    "Sales","Invoice Date","Due Date","Invoice Amount","Balance"]
EH=[""]*26
for i,v in ((9,"Project Number"),(10,"Quotation Number"),(15,"Amount")):EH[i]=v
MH=["Source","Source Date","Synced At KST","Source ID","Rows","Schema","Meaning"]
A="AMEA2026090309"
B="AMEA2026091512"
C="AMEA2026091134"
D="AMEA2026092104"

def watch(amea,unsafe="X209SC26065705-Z01"):
    return [amea,"Korea-example-"+amea,"2026-10","2026-10-08","9640005","6.4","0",
            "OVERDUE_ESTIMATE_NOT_VERIFIED","PROXY","QUOTE_FORECAST",
            "ISSUANCE_NOT_VERIFIED","","H209SC26065705",unsafe,""]

def online(amea,h,x,z=""):
    r=[""]*26
    r[0]="rec"+amea
    r[1]=h
    r[2]=x
    r[6]=z
    r[17]="Korea-example-"+amea
    return r

def finance(amea,raw,source="Outstanding",gross="1287000"):
    r=[""]*(14 if source=="Outstanding" else 26)
    if source=="Outstanding":r[5]=raw;r[7]=amea;r[12]=gross
    else:r[9]=raw;r[10]=amea;r[15]=gross
    return r

def fixture():
    w=[WH,watch(A),watch(B),watch(C),watch(D)]
    o=[OH,online(A,"H209SC26107211","X209SC26107211-Z01","X209SC26107211-Z01-F001"),
       online(B,"H209SC26095539","X209SC26095539-Z01")]
    f=[FH,finance(A,"X209SC26107211"),finance(C,"X209SC26020509")]
    e=[EH,finance(A,"X209SC26107211","eTax")]
    m=[MH,["Online-Project","2026-10-31","","online","2","",""],
       ["Payment Outstanding","2026-10-26","","out","2","",""],
       ["eTax Invoice","2026-10-26","","tax","1","",""]]
    return w,o,f,e,m

class CrosswalkTests(unittest.TestCase):
    def test_candidate_states_and_dedupe(self):
        rows,summary=assess(*fixture(),NOW)
        states={r[0]:r[8] for r in rows}
        self.assertEqual(states[A],"ONLINE_FINANCE_SAME_X_CANDIDATE")
        self.assertEqual(states[B],"ONLINE_AMEA_CANDIDATE")
        self.assertEqual(states[C],"FINANCE_AMEA_CANDIDATE")
        self.assertEqual(states[D],"NO_AMEA_SOURCE_CANDIDATE")
        self.assertEqual(summary["candidate_rows"],3)
        self.assertEqual(summary["original_source_writes"],0)
        self.assertEqual(summary["revenue_writes"],0)
        by={r[0]:r for r in rows}
        self.assertEqual(by[A][4],"H209SC26107211")
        self.assertEqual(by[A][5],"X209SC26107211-Z01")
        self.assertEqual(by[A][7],"X209SC26107211")
        self.assertEqual(by[C][4],"") # no H inferred from a finance-only base key
        self.assertEqual(by[A][12],1287000)
        self.assertEqual(by[A][13],1287000)
        self.assertEqual(by[A][16],"CANDIDATE_ONLY_REQUIRES_ORIGINAL_CONTRACT_REVIEW")

    def test_mismatched_online_and_finance_quarantines(self):
        w,o,f,e,m=fixture()
        f[1][5]="X209SC26065705";e[1][9]="X209SC26065705"
        rows,_=assess(w,o,f,e,m,NOW)
        self.assertEqual(rows[0][8],"ONLINE_FINANCE_X_CONFLICT")
        self.assertEqual(rows[0][16],"QUARANTINE_NO_CONTRACT_ATTRIBUTION")

    def test_multiple_online_contracts_quarantines(self):
        w,o,f,e,m=fixture()
        o.append(online(A,"H209SC26000000","X209SC26000000-Z01"))
        o[-1][0]="rec-alt-"+A  # two distinct Feishu source rows
        m[1][4]="3"
        rows,_=assess(w,o,f,e,m,NOW)
        self.assertEqual(rows[0][8],"AMBIGUOUS_ONLINE_CONTRACT_REVIEW")
        self.assertEqual(rows[0][4],"")
        self.assertEqual(rows[0][5],"")

    def test_global_cross_customer_x_collision_is_quarantined(self):
        w,o,f,e,m=fixture()
        # Same base X appears in a different AMEA's finance record.
        f.append(finance(D,"X209SC26107211",gross="1000"))
        m[2][4]="3"
        rows,_=assess(w,o,f,e,m,NOW)
        by={r[0]:r for r in rows}
        self.assertEqual(by[A][8],"X_REFERENCES_MULTIPLE_AMEAS")
        self.assertEqual(by[D][8],"X_REFERENCES_MULTIPLE_AMEAS")
        self.assertEqual(by[A][16],"QUARANTINE_NO_CONTRACT_ATTRIBUTION")

    def test_manifests_are_count_guarded(self):
        w,o,f,e,m=fixture()
        m[1][4]="5"
        with self.assertRaisesRegex(ValueError,"SOURCE_ROW_DRIFT_Online-Project"):
            assess(w,o,f,e,m,NOW)

    def test_wrong_source_stage_is_refused(self):
        w,o,f,e,m=fixture()
        o[1][6]="X209SC26065705-Z01-F001"
        with self.assertRaisesRegex(ValueError,"ONLINE_STAGE_CONFLICT"):
            assess(w,o,f,e,m,NOW)

    def test_source_x_suffix_never_guessed(self):
        self.assertEqual(xbase("X209SC26107211-Z01-F001"),"X209SC26107211")
        self.assertEqual(xbase("X209SC26107211"),"X209SC26107211")
        with self.assertRaisesRegex(ValueError,"SOURCE_X_SUFFIX_FORMAT"):
            xbase("X209SC26107211-BAD")

    def test_missing_amea_in_online_title_is_not_a_key(self):
        w,o,f,e,m=fixture()
        o[1][17]="Korea-example-without-AMEA"
        rows,_=assess(w,o,f,e,m,NOW)
        self.assertEqual(rows[0][8],"FINANCE_AMEA_CANDIDATE")
        self.assertEqual(rows[0][4],"")

if __name__=="__main__":
    unittest.main()
