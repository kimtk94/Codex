#!/usr/bin/env python3
"""Exact Lead ID joins; no network credentials in tests."""
import sys,pathlib,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import css_mail_local as c

def raw(ids):
    header=[""]*23
    header[12]="Description";header[22]="SFDC Lead ID"
    result=[header]
    for lead_id,desc in ids:
        row=[""]*23;row[12]=desc;row[22]=lead_id
        result.append(row)
    return result
def leads(ids):
    header=[""]*21;header[0]="Lead ID";header[7]="Personal Mail Evidence"
    out=[header]
    for x in ids:
        row=[""]*21;row[0]=x;row[7]="NO_PERSONAL_OUTBOUND_EVIDENCE"
        out.append(row)
    return out
class DescriptionTests(unittest.TestCase):
    def test_both_description_and_no_description(self):
        linked=c.raw_lead_descriptions(raw([("Lead-A","Clinical details"),("Lead-B","")]),
            leads(["Lead-A","Lead-B"]))
        self.assertEqual(linked,{"Lead-A":"Clinical details","Lead-B":""})
    def test_unjoined_lead_never_assumed_blank(self):
        with self.assertRaisesRegex(ValueError,"LEAD_DESCRIPTION_ID_PARITY"):
            c.raw_lead_descriptions(raw([("Lead-A","")]),leads(["Lead-A","Lead-B"]))
    def test_duplicate_source_id_blocks(self):
        with self.assertRaisesRegex(ValueError,"LEAD_RAW_DUPLICATE_ID"):
            c.raw_lead_descriptions(raw([("Lead-A","foo"),("Lead-A","bar")]),
                leads(["Lead-A"]))
    def test_schema_drift_blocks(self):
        r=raw([("Lead-A","")]);r[0][12]="Unknown"
        with self.assertRaisesRegex(ValueError,"LEAD_RAW_DESCRIPTION_SCHEMA"):
            c.raw_lead_descriptions(r,leads(["Lead-A"]))
    def test_long_description_blocks(self):
        with self.assertRaisesRegex(ValueError,"LEAD_DESCRIPTION_TOO_LONG"):
            c.raw_lead_descriptions(raw([("Lead-A","A"*5001)]),leads(["Lead-A"]))
if __name__=="__main__":unittest.main()
