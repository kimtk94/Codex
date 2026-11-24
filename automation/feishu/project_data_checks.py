"""Evidence-labelled project data checks, using already loaded source snapshots.

Advisory only: no business status, financial amount, relationship or user-owned
value is changed by this module. CHECKED means the limited checks below passed,
not that every system agrees, an invoice is paid, or the sources are live/fresh.
"""
from collections import defaultdict
import re

DATA_FIELDS = (
    "PM Source Coverage", "PM Data Check", "PM Quote Link", "PM X Link",
    "PM Status Check", "PM Check Reasons",
)
COVERAGE = "PM Source Coverage"
CURRENT = "CURRENT_INPUT"
CARRYOVER = "CARRYOVER_REVIEW"
AMEA_RE = re.compile(r"AMEA\d{7,}(?:-\d{1,3})?\Z")
X_RE = re.compile(r"X\d+SC\d+(?:-Z\d+)?\Z")
QID_RE = re.compile(r"QID-[0-9-]{8,50}\Z")
QUOTE_ID_RE = re.compile(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\Z")
ACTIVE = {"ACTIVE", "YES", "TRUE", "1"}
HANDOFF = {
    "CSS_EXPLICIT_FINAL_HANDOFF", "LIFECYCLE_EXPLICIT_FINAL_HANDOFF",
    "ALL_SUBPROJECTS_FINAL_REPORT_VERIFIED",
}
PARTIAL = {"PARTIAL_SUBPROJECT_COMPLETION_REVIEW",
           "MULTIPLE_SUBPROJECTS_COMPLETION_REVIEW"}
UNKNOWN_PHASE = "진행 단계 미확인"


def value(row, name):
    val = row.get(name)
    return "" if val is None else str(val).strip()


def quote_id(raw):
    # Salesforce 15-character IDs are case-sensitive. Preserve casing.
    return raw[:15] if QUOTE_ID_RE.fullmatch(raw) else ""


def group(rows, name, upper=True):
    result = defaultdict(list)
    for row in rows:
        key = value(row, name)
        key = key.upper() if upper else key
        if key:
            result[key].append(row)
    return result


def carryover_fields():
    # Do not renew Last Sync KST or keep a historical exact-link label.
    return dict(zip(DATA_FIELDS, (
        CARRYOVER, CARRYOVER, "NOT_RECHECKED", "NOT_RECHECKED",
        "NOT_RECHECKED", "ABSENT_FROM_CURRENT_INPUT",
    )))


class ProjectEvidence:
    def __init__(self, sources):
        self.css = group(sources.get("CSS Project Dashboard", []), "project_id")
        self.sif = group(sources.get("CSS Contract-SIF Tracker", []), "project_id")
        self.life = group(sources.get("BI Project Lifecycle Overview", []), "AMEA")
        self.portfolio = group(sources.get("Quote Portfolio", []), "Approved AMEA ID")
        self.export_qid = group(sources.get("SFDC Quote Export", []), "AMEA Quotation ID")
        self.export_id = defaultdict(list)
        self.x_owners = defaultdict(set)
        self.quote_owners = defaultdict(set)
        self.qid_owners = defaultdict(set)
        for row in sources.get("SFDC Quote Export", []):
            ident = quote_id(value(row, "Salesforce Record ID"))
            if ident:
                self.export_id[ident].append(row)
        for pid, rows in self.life.items():
            for row in rows:
                x = value(row, "Project / Sub-project").upper()
                if X_RE.fullmatch(x):
                    self.x_owners[x].add(pid)
        for pid, rows in self.portfolio.items():
            for row in rows:
                ident = quote_id(value(row, "Salesforce Quote ID (18)"))
                qid = value(row, "Quote QID").upper()
                if ident:
                    self.quote_owners[ident].add(pid)
                if QID_RE.fullmatch(qid):
                    self.qid_owners[qid].add(pid)

    def quote_link(self, pid, board):
        candidates = self.portfolio.get(pid, [])
        approved = [r for r in candidates
                    if value(r, "Active").upper() in ACTIVE
                    and value(r, "Approval Match").upper() == "APPROVED"]
        if not approved:
            return "REVIEW_NO_ACTIVE_APPROVED"
        pairs = {(value(r, "Quote QID").upper(),
                  quote_id(value(r, "Salesforce Quote ID (18)"))) for r in approved}
        if len(pairs) != 1:
            return "CONFLICT_MULTIPLE_QUOTE_IDS"
        qid, ident = next(iter(pairs))
        if not QID_RE.fullmatch(qid) or not ident:
            return "REVIEW_QUOTE_ID_MISSING"
        if self.quote_owners[ident] != {pid} or self.qid_owners[qid] != {pid}:
            return "CONFLICT_QUOTE_SHARED_AMEA"
        # The legacy name-based display cannot prove immutable identity.
        names = {value(r, "Quote Name") for r in approved}
        if names != {value(board, "Quote Full Name")} or "" in names:
            return "CONFLICT_QUOTE_NAME"
        exports = self.export_qid.get(qid, [])
        if not exports:
            return "REVIEW_QUOTE_EXPORT_MISSING"
        if len(exports) != 1 or len(self.export_id.get(ident, [])) != 1:
            return "CONFLICT_QUOTE_EXPORT_AMBIGUOUS"
        export = exports[0]
        if quote_id(value(export, "Salesforce Record ID")) != ident:
            return "CONFLICT_QUOTE_EXPORT_ID"
        if value(export, "IsActive").upper() not in ACTIVE:
            return "CONFLICT_QUOTE_EXPORT_INACTIVE"
        return "EXACT_QUOTE_SNAPSHOT"

    def x_link(self, pid):
        rows = self.life.get(pid, [])
        if not rows:
            return "REVIEW_NO_LIFECYCLE"
        ids = [value(r, "Project / Sub-project").upper() for r in rows]
        if any(x and self.x_owners[x] != {pid} for x in ids if X_RE.fullmatch(x)):
            return "CONFLICT_X_SHARED_AMEA"
        if any(not X_RE.fullmatch(x) for x in ids):
            return "REVIEW_X_ID_MISSING_OR_INVALID"
        if len(ids) != len(set(ids)):
            return "REVIEW_DUPLICATE_X_ROWS"
        # Exact association in the Lifecycle snapshot only. The separate X
        # registry owns authoritative AMEA-H-Online-X-SAM chain validation.
        return "EXACT_LIFECYCLE_ONLY"

    def assess(self, board, phase_of):
        pid = value(board, "AMEA").upper()
        q = self.quote_link(pid, board)
        x = self.x_link(pid)
        reasons = [v for v in (q, x) if not v.startswith("EXACT_")]
        css = self.css.get(pid, [])
        lifecycle = self.life.get(pid, [])
        if len(css) != 1:
            reasons.append("REVIEW_CSS_BASELINE" if not css else "CONFLICT_CSS_DUPLICATE")
        if len(self.sif.get(pid, [])) > 1:
            reasons.append("REVIEW_SIF_DUPLICATE")
        completion = value(board, "Completion Evidence")
        phase = value(board, "Progress Phase")
        phases = {phase_of(value(r, "Feishu Status (latest)") or
                           value(r, "CSS Stage (legacy)")) for r in lifecycle}
        phases.discard(UNKNOWN_PHASE)
        if completion in PARTIAL:
            status = "PARTIAL_HANDOFF_REVIEW"
            reasons.append("REVIEW_PARTIAL_HANDOFF")
        elif completion in HANDOFF:
            # Legacy handoff may mean report/statement READY, not delivered.
            status = "HANDOFF_SIGNAL_ONLY"
        elif not css or phase in {"", UNKNOWN_PHASE}:
            status = "STAGE_UNVERIFIED"
            reasons.append("REVIEW_STAGE_UNVERIFIED")
        elif len(phases) > 1:
            status = "MIXED_X_STAGES"
            reasons.append("REVIEW_MIXED_X_STAGES")
        elif phases and phase not in phases:
            status = "STAGE_DIVERGENCE_REVIEW"
            reasons.append("REVIEW_CSS_LIFECYCLE_STAGE")
        else:
            status = "STAGE_REPORTED"
        if board.get("Progress %") is None:
            reasons.append("REVIEW_PROGRESS_UNKNOWN")
        if completion in HANDOFF and any(p != "05 데이터/리포트" for p in phases):
            reasons.append("REVIEW_HANDOFF_VS_LIFECYCLE")
        check = ("CONFLICT" if any(v.startswith("CONFLICT_") for v in reasons)
                 else "REVIEW" if reasons else "CHECKED")
        return dict(zip(DATA_FIELDS, (
            CURRENT, check, q, x, status, "; ".join(sorted(set(reasons))) or "LIMITED_CHECKS_PASS",
        )))
