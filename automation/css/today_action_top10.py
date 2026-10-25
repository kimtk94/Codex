"""Read-only unified Today Action queue from existing Google Sheet CSV exports.

Inputs: BI Followup Unified and optional Lead Email Followup and Unanswered Emails.
Never edits SFDC, sends mail, or changes source sheets.
"""
import argparse
import csv
from datetime import date, datetime
from pathlib import Path

from next_best_action_leads import classify, parse_date

HEADERS = ["Rank","Priority","Score","Source","Record ID","Institution","Customer","Project ID",
           "Issue","Action","Due Date","Final Contact Date","Verification","Evidence","Source Tab"]
CLOSED = {"DONE","CLOSED","RESOLVED","EXCLUDED","SKIPPED","COMPLETED","CANCELLED","CANCELED"}
BAD = {"#N/A","#REF!","#VALUE!","#ERROR!","N/A","NULL"}


def read_csv(path):
    if not path:
        return []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def clean(value):
    value = str(value or "").strip()
    return "" if value.upper() in BAD else value


def due_bonus(value, today):
    when = parse_date(value)
    return min(15, max(0, (today - when).days)) if when else 0


def css_rows(rows, today):
    output = []
    for row in rows:
        identifier = clean(row.get("Record ID"))
        if not identifier:
            continue
        status = clean(row.get("Original Status")).upper()
        if status in CLOSED:
            continue
        source = clean(row.get("Source")) or "CSS"
        priority = clean(row.get("Priority")).upper()
        score = {"P0":85,"P1":65,"P2":45}.get(priority,35) + due_bonus(row.get("Due / Event Date"),today)
        verification = clean(row.get("Freshness")) or "REVIEW_REQUIRED"
        # Never treat a historical issue as confirmed unresolved.
        if verification != "CURRENT_VERIFIED":
            score = min(score,89)
        output.append({"Priority":priority or "P2","Score":score,"Source":source,
           "Record ID":identifier,"Institution":clean(row.get("Institution")),
           "Customer":clean(row.get("Customer")),"Project ID":clean(row.get("Project ID")),
           "Issue":clean(row.get("Issue / Type")),"Action":clean(row.get("Verification Next Action")) or clean(row.get("Recommended Action")),
           "Due Date":clean(row.get("Due / Event Date")),"Final Contact Date":"",
           "Verification":verification,"Evidence":clean(row.get("Evidence ID")),
           "Source Tab":clean(row.get("Source Tab"))})
    return output


def lead_rows(rows, today):
    output = []
    for row in rows:
        identifier = clean(row.get("Lead ID"))
        if not identifier:
            continue
        status, score, action = classify(row,today)
        if status not in {"P0","P1","P2"}:
            continue
        output.append({"Priority":status,"Score":score,"Source":"LEAD",
            "Record ID":identifier,"Institution":clean(row.get("Institution")),
            "Customer":clean(row.get("Customer")),"Project ID":clean(row.get("Opportunity ID")),
            "Issue":clean(row.get("Description Preview"))[:160],
            "Action":action,"Due Date":clean(row.get("Due Date")),
            "Final Contact Date":clean(row.get("Final Contact Date")),
            "Verification":"NEEDS_MAIL_VERIFICATION","Evidence":clean(row.get("Email")),
            "Source Tab":"Lead Email Followup"})
    return output


def _dedup(rows):
    selected = {}
    for row in rows:
        # Use stable source-specific record ID, never fuzzy customer-only matching.
        key = (row["Source"].upper(),row["Record ID"].upper())
        if key not in selected or row["Score"] > selected[key]["Score"]:
            selected[key] = row
    return list(selected.values())


def build(css, leads, today, limit=10):
    rows = _dedup(css_rows(css,today)+lead_rows(leads,today))
    rows.sort(key=lambda x:(-x["Score"],x["Due Date"] or "9999",x["Source"],x["Record ID"]))
    for i,row in enumerate(rows[:limit],1):
        row["Rank"]=i
    return rows[:limit],len(rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--unified-csv",required=True,type=Path)
    p.add_argument("--lead-csv",type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--today",type=date.fromisoformat,default=date.today())
    p.add_argument("--limit",type=int,default=10)
    args=p.parse_args()
    if args.limit < 1:
        p.error("--limit must be positive")
    result,total=build(read_csv(args.unified_csv),read_csv(args.lead_csv),args.today,args.limit)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(result)
    print(f"TODAY_ACTION_CANDIDATES={total} TOP={len(result)} OUTPUT={args.output}")


if __name__=="__main__":
    main()
