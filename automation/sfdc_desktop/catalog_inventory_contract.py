"""Validate an offline, redacted Salesforce Quote Product Line inventory.

Do not upload authenticated Salesforce HTML, Quote records, customer details,
prices or IDs to CI. CI runs synthetic tests only.
"""
import argparse
import json
import re
from pathlib import Path

SUCCESS = frozenset(("PASS", "DETAIL_CAPTURED", "NEXT_DETAIL_CAPTURED"))
NUMBER = re.compile(r"(?m)^\s*\d+\s*$")


def count_processes(text):
    if not isinstance(text, str) or "Process List" not in text:
        return 0
    return len(NUMBER.findall(text))


def validate_catalog(rows, minimum=1):
    if not isinstance(rows, list):
        raise ValueError("Catalog inventory must be a JSON array")
    seen = set()
    passed = 0
    held = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Invalid row {index}")
        category = row.get("category")
        service = row.get("service")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"Missing category at {index}")
        if not isinstance(service, str) or not service.strip():
            raise ValueError(f"Missing service at {index}")
        key = (category.casefold().strip(), service.casefold().strip())
        if key in seen:
            raise ValueError(f"Duplicate category/service pair at {index}")
        seen.add(key)
        if row.get("save_clicked") is not False or row.get("done_clicked") is not False:
            raise ValueError("Read-only catalog inventory cannot click Done or Save")
        if row.get("state") in SUCCESS or row.get("status") in SUCCESS:
            body = row.get("details", row.get("process_list_text", row.get("detail_text")))
            if count_processes(body) < 1:
                raise ValueError(f"Successful row missing Process List at {index}")
            passed += 1
        else:
            held += 1
    if passed < minimum:
        raise ValueError(f"Only {passed} verified of required {minimum}")
    return {"verified_services": passed, "held_services": held, "unique_rows": len(seen)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--minimum", type=int, default=1)
    args = parser.parse_args()
    rows = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    print(json.dumps(validate_catalog(rows, minimum=args.minimum), sort_keys=True))


if __name__ == "__main__":
    main()
