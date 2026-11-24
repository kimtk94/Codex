# Project data connection & status contract

> Deployment: [INTEGRATED_RELEASE.md](INTEGRATED_RELEASE.md) defines the single-candidate alternative to the historical stacked PR sequence below. Review and approve one route only; CI is not live verification.

## Design boundary

The canonical Project Progress Board remains one AMEA row per source key
`PROJECT:<AMEA>`. The X Project Registry and its link/invoice tables retain
the individual subproject identities. Do not copy AMEA progress or payment
status to X rows or assume that a display name is an identity.

This revision adds a scoped, advisory data check to the existing project board
writer and its native project center. It reuses the inputs already loaded by
`sales_metrics_sync.py`; it does not introduce another API poll, scheduler,
source, reconciliation writer, payment rule, or customer notification.

## Relationship acceptance

| Relationship | Authority / acceptance criterion | Review / reject |
| --- | --- | --- |
| Account/Contact/Opportunity/Quote | Salesforce object and relationship IDs | Names or email/domain hints alone |
| Quote -> AMEA | approved active Quote Portfolio with unique exact AMEA, QID and case-sensitive Salesforce Quote ID; matching unique active SFDC Quote Export QID/ID | missing key, shared AMEA, multiple IDs, conflicting name/export, inactive |
| AMEA -> H -> X | existing x_project_lineage.py: exact CSS H, Online-Project H/X, explicit Lifecycle X/AMEA | unique-H candidate is still only a candidate; conflicting X ownership |
| X -> SAM | existing x_project_lineage.py: current CSS SAM + unique official X + no shared SAM | timeline-only, shared SAM, multiple X; no automatic cross-product |
| Mail -> project | existing mail/PO owner-source checks: original trusted event, exact unique subject/project key, review if uncertain | reply/forward, ambiguous ID, name-only candidate |
| AMEA/X -> CMS Invoice | existing latest_payment_bridge.py: exact CMS/AMEA/X/VAT-inclusive amount and source owner evidence | conflicting scope/amount, missing ID |
| Invoice -> Receipt | existing latest_payment_bridge.py and project_settlement.py: exact CMS amount/date and current balance; manual bank/ERP attestation where permitted | positive balance, conflicting invoice set/gross, missing or historical proof |

The new board check assesses **only Quote Portfolio vs Quote Export and exact
Lifecycle AMEA/X snapshot relationships**, plus CSS baseline/SIF multiplicity,
phase consistency and progress presence. Full H/SAM, mail, PO and financial
evidence remain in their existing authoritative components, and must not be
inferred from the limited board check. Multiple distinct X under one AMEA are
valid; the number of X rows must not be interpreted as AMEA count or proof of
completeness. It checks all snapshot rows, not live system completeness.

## Fields

| Field | Values / interpretation |
| --- | --- |
| PM Source Coverage | CURRENT_INPUT: projected in this run's input; CARRYOVER_REVIEW: previously stored, absent from this run's input |
| PM Data Check | CONFLICT: identity contradictions; REVIEW: missing, duplicate or uncertain evidence; CHECKED: limited checks pass; CARRYOVER_REVIEW: not rechecked |
| PM Quote Link | EXACT_QUOTE_SNAPSHOT, REVIEW_*, CONFLICT_*; NOT_RECHECKED for carryover |
| PM X Link | EXACT_LIFECYCLE_ONLY, REVIEW_*, CONFLICT_*; NOT_RECHECKED for carryover |
| PM Status Check | STAGE_REPORTED, STAGE_DIVERGENCE_REVIEW, MIXED_X_STAGES, STAGE_UNVERIFIED, HANDOFF_SIGNAL_ONLY, PARTIAL_HANDOFF_REVIEW, NOT_RECHECKED |
| PM Check Reasons | Deterministic reason codes; LIMITED_CHECKS_PASS is not a global integrity certificate |

Priority: CONFLICT outranks REVIEW; no unsupported relation is auto-created.
CHECKED does not certify source freshness, actual delivery, payment or all
links. Case-sensitive Salesforce ID comparison preserves the first 15
characters, following the existing board ID convention. The immutable ID
check is distinct from legacy name-based Quote Match State. No source record,
relationship, amount, manually managed field or receipt attestation is
rewritten by the advisory check.

## State acceptance and transition rules

| State | Evidence required / interpretation |
| --- | --- |
| Contract / PO | original contract event; verified PO file requires the existing tracker manual file reference, verifier and time; a final-report or statement signal is not a PO receipt |
| SIF | distinguish number only, submitted, approved, prepayment waiver; later physical stage can remove obsolete reminder without claiming SIF receipt |
| Sample/QC, library, sequencing | explicit source stage; failed/abnormal/resend requires action; progress is source-reported, not elapsed time or number of emails |
| Data processing | demultiplexing, Data QC, BI Analysis mapped to data/report phase (not Sample QC) |
| Handoff | canonical legacy report/statement-ready, sent or completed signal; HANDOFF_SIGNAL_ONLY is not proof of customer delivery/acceptance |
| Multi-X | mixed or incomplete evidence is review; do not infer completion for unobserved subprojects |
| Payment | use canonical Payment State and Workflow Lane; completion, issued invoice, zero/blank balance and verified receipt are distinct |
| Archive | existing finalized receipt and completion rules remain; no closure/reopen inferred from a missing source row |
| Human management | manual status/priority/owner/date/notes are not production or financial proof |

The board retains existing completion/handoff semantics; this revision flags
evidence quality, not a replacement business definition of delivered or paid.
A valid zero percent is not missing. For a current projected board row, if
numeric progress is unknown, explicitly clear stale prior numeric progress.
Never change a known historical progress value solely because a record is
absent from the latest input.

## Freshness and completeness

- CURRENT_INPUT is membership in the last successfully projected input, not
  proof that the original source is current or the range is exhaustive.
- Last Sync KST remains the existing writer's last changed-row time, not a
  universal "last checked" time. A carryover-only update never renews it.
- Keep source issue/snapshot dates, source-received times, mirror-sync times,
  execution/readback times and actual milestone dates distinct.
- Existing Payment manifest checks (72-hour mirror, 45-day dated-source
  bound; schema proof) and X registry Online manifest check (48-hour mirror)
  remain in their owners. These are technical checks, not business SLAs or
  evidence that the newest live source was fetched by this advisory layer.
- Successful sync of a mirror cannot cure stale original evidence; a failed
  or missing source must never be interpreted as paid, delivered, zero or
  canceled. The new check does not add a source-wide freshness certification.

## Views & native project page

The writer provisions three active-project grid views: 05 연결 충돌, 06 연결 확인,
07 이전 원본 보존. The native project page shows current-input active/payment
counts and charts, two evidence distributions, and distinct carryover and
unclassified counts. Payment charts preserve MY_VERIFIED scope. Historical
archive counts retain their historical meaning. Existing detail views remain.

An absent canonical project is marked for review only if the desired input is
nonempty and contains consistent canonical project keys with the new coverage
field. It is not deleted, archived, moved, or re-dated. Reappearance in a
later input replaces the advisory fields and re-evaluates evidence. Existing
manual management/finance fields and original last-change time are untouched
by carryover updates.

## Deployment and verification

Stacked after #1044, #1047 and #1051. Review and merge these in order; do not
deploy partial page contracts. Run the existing Sources Unified writer on main
with authenticated source verification, confirm schema/view and record
readback, then use the project-center plan/explicit apply/verify workflow.
Review actual data quality distributions, source age, retained row counts and
new field coverage before relying on the page. No live write or actual
customer-row inspection was performed while preparing this change.

Follow-up: join the authoritative X registry, PO tracker, and per-source
freshness proofs in an independently validated read layer. Add TAT/customer
promised date and actual delivery milestones only when exact scope and dates
are verified. Maintain separate SLA policy and human override history.
