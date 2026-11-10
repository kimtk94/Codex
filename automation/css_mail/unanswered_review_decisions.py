#!/usr/bin/env python3
"""Persistent, opt-in skip decisions for the QQ 60-day reply review.

A decision skips one canonical IMAP message. A routing rule skips only
mail addressed to somebody else with the owner on CC, and matches an
explicit exact sender or To address. Everything else remains reviewable.

No email, IMAP flags, SFDC records, or legacy exclusion ledgers are changed.
"""
import datetime as dt
import re
from collections import Counter
from email.utils import getaddresses

DECISIONS_TAB = "Unanswered Reply Decisions"
RULES_TAB = "Unanswered Reply Routing Rules"
DECISION_HEAD = [
    "Active (Edit)", "Decision", "Canonical Ingest Key", "Mail UID",
    "Customer Email", "Subject", "Reviewer Note", "Recorded UTC",
]
RULE_HEAD = [
    "Active (Edit)", "Rule Type (Edit)", "Exact Address (Edit)",
    "Condition", "Action", "Reviewer Note", "Created From Mail", "Recorded UTC",
]
APPEND_HEAD = [
    "Receipt Role", "Action (Edit)", "Rule Target Address (Edit)",
    "Reviewer Note (Edit)", "Action State",
]
ACTIONS = frozenset(("SKIP_MAIL", "SKIP_CC_TO", "SKIP_CC_SENDER"))
MAIL_KEY_IDX = 14
UID_IDX = 10
FROM_IDX = 3
SUBJECT_IDX = 4
TO_IDX = 12
CC_IDX = 13
ACTION_IDX = 20
TARGET_IDX = 21
NOTE_IDX = 22
EMAIL_RE = re.compile(r"^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$")


def cell(row, i):
    return str(row[i] if len(row) > i and row[i] is not None else "").strip()


def truth(value):
    return str(value or "").strip().upper() in ("TRUE", "YES", "1")


def emails(value):
    return {a.casefold() for _, a in getaddresses([str(value or "")]) if a}


def exact_email(value):
    value = str(value or "").strip().casefold()
    if not EMAIL_RE.fullmatch(value):
        raise ValueError("RULE_ADDRESS_MUST_BE_ONE_EXACT_EMAIL")
    return value


def validate_ledger(rows, expected):
    if not rows or list(rows[0]) != list(expected):
        raise RuntimeError("REVIEW_LEDGER_SCHEMA_CHANGED")
    return rows[1:]


def cc_only(row, owner):
    own = emails(owner)
    return bool(own and (own & emails(cell(row, CC_IDX))) and
                not (own & emails(cell(row, TO_IDX))))


def receipt_role(row, owner):
    own = emails(owner)
    if own & emails(cell(row, TO_IDX)):
        return "TO"
    if own & emails(cell(row, CC_IDX)):
        return "CC_ONLY"
    return "NOT_ADDRESSED_TO_OWNER"


def active_mail_keys(rows):
    data = validate_ledger(rows, DECISION_HEAD)
    keys = set()
    for row in data:
        if not truth(cell(row, 0)):
            continue
        if cell(row, 1) != "SKIP_MAIL" or not cell(row, 2):
            raise RuntimeError("INVALID_ACTIVE_MAIL_DECISION")
        keys.add(cell(row, 2))
    return keys


def active_rules(rows):
    data = validate_ledger(rows, RULE_HEAD)
    rules = set()
    for row in data:
        if not truth(cell(row, 0)):
            continue
        typ = cell(row, 1).upper()
        addr = exact_email(cell(row, 2))
        if typ not in ("TO_ADDRESS", "SENDER_ADDRESS") or (
            cell(row, 3) != "OWNER_CC_ONLY" or cell(row, 4) != "SKIP"
        ):
            raise RuntimeError("INVALID_ACTIVE_CC_ROUTING_RULE")
        rules.add((typ, addr))
    return rules


def rule_for(row, owner, rules):
    if not cc_only(row, owner):
        return ""
    tos = emails(cell(row, TO_IDX))
    senders = emails(cell(row, FROM_IDX))
    if any((typ == "TO_ADDRESS" and addr in tos) for typ, addr in rules):
        return "SKIPPED_CC_TO_RULE"
    if any((typ == "SENDER_ADDRESS" and addr in senders) for typ, addr in rules):
        return "SKIPPED_CC_SENDER_RULE"
    return ""


def plan(queue, current_candidates, decision_rows, rule_rows, owner, now=None):
    """Validate edits BEFORE writing. Return two sets of append-only entries.

    Never use a visible row number as identity. The canonical IMAP key must
    still exist, and snapshot sender/subject/To/CC must match current evidence.
    """
    valid_headers = len(queue) > 0 and len(queue[0]) >= 19 and (
        queue[0][14] == "Canonical Ingest Key"
    )
    if not valid_headers:
        raise RuntimeError("REVIEW_QUEUE_SCHEMA_CHANGED")
    if len(queue[0]) not in (19, 24):
        raise RuntimeError("REVIEW_QUEUE_HEADER_UNSUPPORTED")
    if len(queue[0]) == 24 and list(queue[0][19:]) != APPEND_HEAD:
        raise RuntimeError("REVIEW_QUEUE_EDIT_COLUMNS_CHANGED")
    prior_mail = active_mail_keys(decision_rows)
    prior_rules = active_rules(rule_rows)
    mapping = {cell(row, MAIL_KEY_IDX): row for row in current_candidates}
    made_mail, made_rules = [], []
    new_mail = set()
    new_rules = set()
    at = (now or dt.datetime.now(dt.timezone.utc)).isoformat()
    for row in queue[1:]:
        action = cell(row, ACTION_IDX).upper() if len(queue[0]) == 24 else ""
        if not action:
            continue
        if action not in ACTIONS:
            raise ValueError("INVALID_QUEUE_ACTION")
        key = cell(row, MAIL_KEY_IDX)
        current = mapping.get(key)
        if not key or current is None:
            raise RuntimeError("STALE_QUEUE_ACTION_REFERENCE")
        if any(cell(row, idx) != cell(current, idx) for idx in (
            UID_IDX, FROM_IDX, SUBJECT_IDX, TO_IDX, CC_IDX
        )):
            raise RuntimeError("QUEUE_ACTION_SNAPSHOT_CHANGED")
        note = cell(row, NOTE_IDX)[:500]
        if action == "SKIP_MAIL":
            if key not in prior_mail and key not in new_mail:
                made_mail.append([
                    "TRUE", "SKIP_MAIL", key, cell(row, UID_IDX),
                    cell(row, FROM_IDX), cell(row, SUBJECT_IDX),
                    note, at,
                ])
                new_mail.add(key)
            continue
        if not cc_only(current, owner):
            raise ValueError("CC_RULE_REQUIRES_OWNER_CC_ONLY")
        if action == "SKIP_CC_TO":
            address = exact_email(cell(row, TARGET_IDX))
            if address not in emails(cell(current, TO_IDX)) or address in emails(owner):
                raise ValueError("CC_TO_RULE_ADDRESS_NOT_IN_TO")
            identity = ("TO_ADDRESS", address)
        else:
            senders = emails(cell(current, FROM_IDX))
            if len(senders) != 1:
                raise ValueError("CC_SENDER_RULE_NEEDS_ONE_SENDER")
            address = exact_email(next(iter(senders)))
            supplied = cell(row, TARGET_IDX)
            if supplied and exact_email(supplied) != address:
                raise ValueError("CC_SENDER_RULE_TARGET_MISMATCH")
            identity = ("SENDER_ADDRESS", address)
        if identity not in prior_rules and identity not in new_rules:
            made_rules.append([
                "TRUE", identity[0], identity[1], "OWNER_CC_ONLY",
                "SKIP", note, key, at,
            ])
            new_rules.add(identity)
    return made_mail, made_rules


def filtered_queue(candidates, decisions, rules, owner):
    skipped = active_mail_keys(decisions)
    routing = active_rules(rules)
    stats = Counter()
    result = []
    for row in candidates:
        key = cell(row, MAIL_KEY_IDX)
        if key in skipped:
            stats["SKIPPED_MAIL"] += 1
            continue
        reason = rule_for(row, owner, routing)
        if reason:
            stats[reason] += 1
            continue
        role = receipt_role(row, owner)
        stats["VISIBLE_" + role] += 1
        current = list(row)
        current[18] = "Unanswered Reply Decisions / Routing Rules"
        result.append(current + [role, "", "", "", "REVIEW"])
    stats["QUEUE_VISIBLE"] = len(result)
    stats["ACTIVE_MAIL_DECISIONS"] = len(skipped)
    stats["ACTIVE_CC_RULES"] = len(routing)
    return result, stats


def guide():
    return [
        ["Action", "Use", "Effect / Restore"],
        ["SKIP_MAIL", "Select in review queue column U",
         "Skip only this exact message; restore: set Active to FALSE in Unanswered Reply Decisions"],
        ["SKIP_CC_TO", "Choose U, put recipient address from To column M into V",
         "Skip future emails to that exact person only if your mailbox is CC-only; disable rule with Active FALSE"],
        ["SKIP_CC_SENDER", "Choose U; sender email auto-detected from column D",
         "Skip future emails from this sender only if your mailbox is CC-only; disable rule with Active FALSE"],
        ["REVIEW", "Leave Action blank",
         "Mail remains in the review queue; no automatic email is sent"],
        ["NEXT SYNC", "Runs after QQ ingest and twice on weekdays",
         "Selected actions are recorded in separate append-only decision/rule tables"],
        ["SAFETY", "To includes your mailbox",
         "CC-only routing NEVER skips messages directly addressed to you"],
    ]
