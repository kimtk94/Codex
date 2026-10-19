#!/usr/bin/env python3
"""Run independent synthetic controls. Does NOT load production CSS."""
import json
import subprocess
import sys
from pathlib import Path

TESTS = (
    ("os_sandbox_negative_controls.py", [], "SANDBOX_NEGATIVE_CONTROLS_PASS True"),
    ("css_source_admission.py", ["--selftest"], "CSS_SOURCE_ADMISSION_SELFTEST_PASS"),
    ("synthetic_adapter_contract.py", [], "CSS_SYNTHETIC_ADAPTER_CONTRACT_PASS"),
)

def main():
    root = Path(__file__).resolve().parent
    results = []
    for filename, args, marker in TESTS:
        completed = subprocess.run(
            [sys.executable, str(root / filename), *args],
            text=True, capture_output=True, timeout=60, check=False,
        )
        passed = completed.returncode == 0 and any(line.startswith(marker) for line in completed.stdout.splitlines())
        results.append({"name": filename, "pass": passed, "exit_code": completed.returncode})
        print("CSS_P0_TEST_RESULT", filename, "PASS" if passed else "FAIL", flush=True)
        if not passed:
            print(completed.stdout[-1000:], file=sys.stderr)
            print(completed.stderr[-1000:], file=sys.stderr)
            print("CSS_P0_SYNTHETIC_ISOLATION_GATE_FAIL", json.dumps(results), flush=True)
            raise SystemExit(1)
    print("CSS_P0_SYNTHETIC_ISOLATION_GATE_PASS", json.dumps(results, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
