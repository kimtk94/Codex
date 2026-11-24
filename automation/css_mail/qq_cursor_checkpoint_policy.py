#!/usr/bin/env python3
"""Pure, read-only rules for conservative QQ IMAP cursor checkpoints.

DO NOT import this module as authorization to write a QQ cursor or invoice.
Promoting a cursor in the writer requires a separate reviewed change.
"""
import ast
from collections import Counter

RESOLVED = frozenset({
    "KNOWN_UID_WITH_VALID_EVIDENCE",
    "ORIGINAL_ISSUED_PROOF_PERSISTED",
    "ORIGINAL_NONOFFICIAL_HEADER_VERIFIED",
})
UNRESOLVED = frozenset({
    "FETCH_FAILED", "MIME_PARSER_UNRESOLVED", "AMOUNT_CONFLICT",
    "ORIGINAL_HEADER_UNAVAILABLE", "UNKNOWN", "UIDVALIDITY_CHANGED",
})


def conservative_cursor(checkpoint, candidates, outcomes):
    """Return maximum *contiguously resolved* candidate UID; never skip a gap.

    The caller must provide a validated, ascending candidate UID list for the
    currently selected mailbox/UIDVALIDITY. All outcomes must be explicitly
    classified. This function performs no side effects.
    """
    if not isinstance(checkpoint, int) or checkpoint < 0:
        raise ValueError("CHECKPOINT_INVALID")
    ids = list(candidates)
    if ids != sorted(set(ids)) or any(
        not isinstance(x, int) or x <= checkpoint for x in ids
    ):
        raise ValueError("CANDIDATE_ORDER_OR_SCOPE_INVALID")
    if not isinstance(outcomes, dict):
        raise ValueError("OUTCOME_MAP_INVALID")
    if set(outcomes) != set(ids):
        raise ValueError("OUTCOME_COVERAGE_INCOMPLETE")
    out = checkpoint
    counts = Counter()
    blocked = False
    for uid in ids:
        state = outcomes[uid]
        if state not in RESOLVED | UNRESOLVED:
            raise ValueError("OUTCOME_UNKNOWN")
        counts[state] += 1
        if state not in RESOLVED:
            blocked = True
        if not blocked:
            out = uid
    return {
        "checkpoint_start": checkpoint,
        "checkpoint_safe": out,
        "checkpoint_would_advance": out > checkpoint,
        "unresolved_count": sum(counts[k] for k in UNRESOLVED),
        "blocked": blocked,
        "source_writes": 0,
        "cursor_writes": 0,
    }


def assess_writer_cursor_order(source):
    """Read-only static guard finding a specific known early-advance pattern.

    AST-level check rejects missing structural evidence rather than asserting
    the writer is safe. Does not expose file contents to GitHub logs.
    """
    tree = ast.parse(source)
    start = []
    fetch = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and (
                    t.value.id == "last_by_folder"
                ):
                    start.append(node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "uid" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and arg.value == "FETCH":
                    fetch.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            # The hardened writer delegates original-header/MIME FETCH
            # handling to a separately tested, side-effect-free helper.
            if node.func.id == "evaluate_candidate":
                fetch.append(node.lineno)
    if not start or not fetch:
        raise ValueError("WRITER_CURSOR_ORDER_UNVERIFIED")
    # This is a vulnerability detector, not an exhaustive proof of writer safety.
    return {
        "early_cursor_advance_detected": min(start) < min(fetch),
        "cursor_safety_review_required": min(start) < min(fetch),
        "writer_mutated": False,
    }
