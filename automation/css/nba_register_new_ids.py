"""Append-only registration for new NBA candidates.

Never sorts or rewrites existing checkbox rows. New (Source, Record ID) pairs
are appended with unchecked state. Designed for use before refreshing Pool
data, preserving existing decision-row identity.
"""
import argparse
import csv
from pathlib import Path


def normalize(value):
    return str(value or "").strip().upper()


def record_key(row):
    source = normalize(row.get("Source"))
    record_id = normalize(row.get("Record ID"))
    if not source or not record_id:
        raise ValueError("Missing Source or Record ID")
    return (source, record_id)


def register(existing, pool):
    registered = set()
    output = []
    for row in existing:
        k = record_key(row)
        if k in registered:
            raise ValueError("Duplicate checkbox key: " + "|".join(k))
        registered.add(k)
        output.append({"Source":row["Source"],"Record ID":row["Record ID"],
                       "완료 체크":str(row.get("완료 체크","FALSE"))})
    added = 0
    for row in pool:
        k = record_key(row)
        if k in registered:
            continue
        registered.add(k)
        output.append({"Source":row["Source"],"Record ID":row["Record ID"],
                       "완료 체크":"FALSE"})
        added += 1
    return output, added


def load(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames or not {"Source","Record ID"}.issubset(reader.fieldnames):
            raise ValueError("CSV missing Source / Record ID headers")
        return list(reader)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--checkboxes",type=Path,required=True)
    p.add_argument("--pool",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    registered,added=register(load(a.checkboxes),load(a.pool))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["Source","Record ID","완료 체크"])
        writer.writeheader()
        writer.writerows(registered)
    print(f"NBA_REGISTERED={len(registered)} ADDED={added}")


if __name__=="__main__":
    main()
