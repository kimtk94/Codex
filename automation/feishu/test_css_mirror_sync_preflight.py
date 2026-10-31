"""Offline, network-free guards for Feishu mirror conditional sync."""
import unittest
from css_mirror_sync_preflight import SCHEMAS,FIELDS,preflight

def source():
    result={}
    for index,(name,schema) in enumerate(SCHEMAS.items()):
        result[name]={"schema":schema,"source_id":"source-"+str(index),
                      "source_date":"2026-10-31","headers":["Field","Amount"],
                      "rows":[["one","100"],["two","200"]]}
    return result

def manifest(snapshots):
    return [FIELDS.copy()]+[
        [name,obj["source_date"],"2026-10-31T22:39:24+09:00",
         obj["source_id"],str(len(obj["rows"])),obj["schema"],"raw unverified"]
        for name,obj in snapshots.items()]

class FeishuMirrorPreflightTests(unittest.TestCase):
    def test_current_five_sources_are_noop(self):
        s=source()
        self.assertEqual(preflight(s,manifest(s)),[])
    def test_new_etax_date_triggers_refresh(self):
        s=source()
        m=manifest(s)
        row=next(x for x in m if x[0]=="eTax Invoice")
        row[1]="2026-10-26"
        self.assertEqual(preflight(s,m),["eTax Invoice:SOURCE_DATE"])
    def test_new_source_id_and_added_records_trigger_refresh(self):
        s=source()
        m=manifest(s)
        s["Payment Receipt"]["source_id"]="new-id"
        s["Payment Receipt"]["rows"].append(["three","300"])
        self.assertEqual(set(preflight(s,m)),
                         {"Payment Receipt:SOURCE_ID","Payment Receipt:ROW_COUNT"})
    def test_source_schema_regression_blocks_write(self):
        s=source()
        s["eTax Invoice"]["schema"]="RAW_GRID_REVIEW"
        with self.assertRaisesRegex(ValueError,"REFUSE_UNRECOGNIZED_SOURCE_SCHEMA"):
            preflight(s,manifest(s))
    def test_manifest_foreign_or_duplicate_source_blocks_write(self):
        s=source()
        m=manifest(s)
        m.append(m[1][:])
        with self.assertRaisesRegex(ValueError,"MIRROR_MANIFEST_FOREIGN_OR_DUPLICATE_SOURCE"):
            preflight(s,m)
        m=manifest(s)
        m[0][0]="Identifier"
        with self.assertRaisesRegex(ValueError,"MIRROR_MANIFEST_FOREIGN_SCHEMA"):
            preflight(s,m)
    def test_missing_manifest_or_row_is_recognized_without_approval(self):
        s=source()
        self.assertEqual(preflight(s,[]),["MANIFEST_MISSING"])
        m=manifest(s)
        m=[m[0]]+[r for r in m[1:] if r[0]!="eTax Invoice"]
        self.assertEqual(preflight(s,m),["eTax Invoice:MISSING"])
    def test_missing_or_duplicate_raw_source_blocks_write(self):
        s=source()
        del s["Online-Project"]
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_FEISHU_SOURCE_SET"):
            preflight(s,manifest(source()))
        s=source()
        s["Payment Outstanding"]["headers"]=["Field","Field"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SOURCE_COLUMN"):
            preflight(s,manifest(s))

if __name__=="__main__":
    unittest.main()
