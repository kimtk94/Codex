import unittest
from research.quant_stack.us_preflight_entry_gate import decide_entry_gate


class GateTests(unittest.TestCase):
    def test_matrix(self):
        cases = [
            (True, True, True, False, True, "ENTRY_GATE_PASS"),
            (False, True, True, False, False, "DRIVE_PREFLIGHT_FAILED"),
            (True, False, True, False, False, "PIPELINE_INCOMPLETE"),
            (True, True, False, False, False, "STALE_OR_MISSING_SIGNAL"),
            (True, True, True, True, False, "EMERGENCY_STOP_ENTRIES"),
        ]
        for pre, pipe, fresh, stop, allowed, reason in cases:
            with self.subTest(reason=reason):
                d = decide_entry_gate(preflight_ok=pre, pipeline_ok=pipe,
                                      fresh_signal=fresh, emergency_stop=stop)
                self.assertEqual(d.new_entry_allowed, allowed)
                self.assertTrue(d.exit_management_allowed)
                self.assertEqual(d.reason, reason)


if __name__ == "__main__":
    unittest.main()
