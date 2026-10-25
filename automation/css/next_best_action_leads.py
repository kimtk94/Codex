"""Read-only prioritization of SFDC Lead Email Followup exports.

Input: CSV exported from 'Lead Email Followup' (header names preserved).
Output: ranked actionable CSV. Does not send mail or mutate SFDC/Sheets.
"""
import argparse
import csv
from datetime import date, datetime
from pathlib import Path


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value).strip()[:10])
        except ValueError:
            return None


def present(value):
    return bool(str(value or "").strip())


def classify(row, today):
    decision = str(row.get("Decision Effective") or "").strip().upper()
    bucket = str(row.get("Action Bucket") or "").strip().upper()
    manual = str(row.get("Manual Status") or "").strip().upper()
    lead_status = str(row.get("Lead Status") or "").strip().upper()
    opp = row.get("Opportunity ID")
    converted = str(row.get("Converted Date") or "").strip()
    sent_count = str(row.get("Sent Mail Count") or "0").strip()
    sent = str(row.get("Sent Mail Status") or "").upper() == "SENT_CONFIRMED"
    try:
        sent = sent or int(float(sent_count)) > 0
    except ValueError:
        pass
    if decision in {"DONE", "CLOSED", "EXCLUDED", "SKIP", "RESOLVED"} or manual in {"DONE", "CLOSED", "EXCLUDED"}:
        return "CLOSED", 0, "Decision 완료: 실행 목록 제외"
    if bucket in {"CONTACTED", "DONE", "EXCLUDED"} or sent:
        return "CONTACTED", 0, "발신 기록 확인: 마지막 연락일 표시"
    if present(opp) or converted.upper() == "CONVERTED" or lead_status in {"CONVERTED", "QUALIFIED"} and present(opp):
        return "OPPORTUNITY", 0, "전환된 Lead: Opportunity에서 관리"
    description = str(row.get("Description Class") or "").upper()
    text = str(row.get("Description Preview") or "").strip()
    has_description = description == "DESCRIPTION_PRESENT" or (not description and bool(text))
    due = parse_date(row.get("Due Date"))
    age = (today - due).days if due else None
    issue = str(row.get("Due State") or "").upper()
    score = 35 if has_description else 10
    if age is not None and age >= 0:
        score += 25 + min(age, 14)  # Cap old overdue leads: no infinite aging dominance.
    if issue == "OVERDUE":
        score += 8
    if str(row.get("Description Intent") or "").upper() == "SERVICE_INQUIRY":
        score += 15
    if not present(row.get("Email")):
        score -= 15
    score = max(0, min(100, score))
    return ("P0" if score >= 75 else "P1" if score >= 50 else "P2"), score, (
        "문의내용 기반 고객 회신 확인 및 연락" if has_description else "전달성 Lead: 내용 확인"
    )


def run(source, destination, today):
    with source.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "Lead ID" not in reader.fieldnames:
            raise ValueError("Expected Lead Email Followup export with 'Lead ID' column")
        rows = []
        for row in reader:
            status, score, action = classify(row, today)
            if status in {"CLOSED", "CONTACTED", "OPPORTUNITY"}:
                continue
            out = dict(row)
            out["NBA Priority"] = status
            out["NBA Score"] = score
            out["NBA Action"] = action
            rows.append(out)
        rows.sort(key=lambda r: (-r["NBA Score"], r.get("Due Date") or "9999", r.get("Lead ID") or ""))
        fields = list(reader.fieldnames) + ["NBA Priority", "NBA Score", "NBA Action"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = p.parse_args()
    count = run(args.input, args.output, args.today)
    print(f"NBA_ACTIONABLE={count} OUTPUT={args.output}")


if __name__ == "__main__":
    main()
