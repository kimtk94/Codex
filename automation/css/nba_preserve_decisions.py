"""Preserve manual NBA decisions when rebuilding the Action Pool snapshot.

The checkbox is keyed by (Source, Record ID), never by spreadsheet row.
Input/Output CSVs use the exact headers of 'NBA Action Pool'.
No Google Sheet mutation is performed by this utility.
"""
import argparse
import csv
from pathlib import Path

KEYS = ("Source", "Record ID")
CHECK = "완료 체크"
REQUIRED = (*KEYS, CHECK)


def key(row):
    return tuple(str(row.get(field, "") or "").strip().upper() for field in KEYS)


def flag(value):
    return str(value or "").strip().upper() in {"TRUE", "1", "YES", "DONE"}


def merge_decisions(current_rows, incoming_rows):
    completed = {key(row) for row in current_rows if all(key(row)) and flag(row.get(CHECK))}
    incoming_keys = set()
    merged = []
    for row in incoming_rows:
        item = key(row)
        if not all(item):
            raise ValueError("Incoming candidate missing Source or Record ID")
        if item in incoming_keys:
            raise ValueError("Duplicate incoming candidate: " + "|".join(item))
        incoming_keys.add(item)
        new = dict(row)
        new[CHECK] = "TRUE" if item in completed or flag(row.get(CHECK)) else "FALSE"
        merged.append(new)
    return merged, {"previously_completed": len(completed),
                    "preserved": len(completed & incoming_keys),
                    "completed_not_in_new_snapshot": len(completed - incoming_keys)}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or any(header not in reader.fieldnames for header in REQUIRED):
            raise ValueError("CSV must have headers: " + ", ".join(REQUIRED))
        return reader.fieldnames, list(reader)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--incoming", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    old_columns, old = read(args.current)
    new_columns, incoming = read(args.incoming)
    rows, audit = merge_decisions(old, incoming)
    # Protect existing schema and the checkbox column; helper formulas are sheet-managed.
    fields = list(dict.fromkeys(new_columns + [CHECK]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print("NBA_DECISION_MERGE", audit, "output", args.output)


if __name__ == "__main__":
    main()
