#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lead_single_select_migration as m

class LeadSelectMigrationTests(unittest.TestCase):
    def fixture(self):
        fields = [
            {"field_name": name, "field_id": "fld" + str(i), "type": 1}
            for i, name in enumerate(m.TARGETS)
        ] + [{"field_name": name, "field_id": "man" + str(i), "type": 7}
             for i, name in enumerate(m.manual.MANUAL)]
        rows = [{"record_id": str(i), "fields": {
            "Lead ID": "00Q-" + str(i),
            **{name: allowed[i % len(allowed)]
               for name, allowed in m.TARGETS.items()},
            **{name: False for name in m.manual.MANUAL},
        }} for i in range(450)]
        return fields, rows

    def test_existing_values_fit_single_select(self):
        fields, rows = self.fixture()
        schema, counts = m.validate(rows, fields)
        self.assertEqual(len(schema), 6)
        self.assertEqual(sum(counts["Description 있음"].values()), 450)

    def test_unknown_value_blocks_migration(self):
        fields, rows = self.fixture()
        rows[0]["fields"]["연락 구분"] = "unknown"
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN_VALUE"):
            m.validate(rows, fields)

    def test_user_fields_are_never_changed(self):
        fields, rows = self.fixture()
        baseline = m.snapshot(rows)
        self.assertEqual(m.parity(baseline, m.snapshot(rows)), 450)
        rows[0]["fields"]["검토 완료"] = True
        with self.assertRaisesRegex(RuntimeError, "UNRELATED_FIELD_CHANGED"):
            m.parity(baseline, m.snapshot(rows))

    def test_option_change_is_rejected(self):
        fields, rows = self.fixture()
        baseline = m.snapshot(rows)
        rows[0]["fields"]["Description 있음"] = "알 수 없음"
        with self.assertRaisesRegex(RuntimeError, "OPTION_VALUE_LOST"):
            m.parity(baseline, m.snapshot(rows))

if __name__ == "__main__":
    unittest.main()
