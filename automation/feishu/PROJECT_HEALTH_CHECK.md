# Project Health Check

> Deployment: [INTEGRATED_RELEASE.md](INTEGRATED_RELEASE.md) defines the single-candidate alternative to the historical stacked PR sequence below. Review and approve one route only; CI is not live verification.

## Purpose

Cross-check the existing project management board with the current X registry,
AMEA/H/X/SAM link table, X Invoice Ledger, Contract PO Tracker and Mail Identity
2026. Read the two existing source-metadata sheets. This is a read-only diagnostic,
not another canonical writer or a source of customer, financial or delivery truth.
It adds no Feishu record, view, table, dashboard, or recurring schedule.

## Evidence rules

| Area | Acceptance | Limitation |
| --- | --- | --- |
| Board | Canonical AMEA/Source Key; CURRENT_INPUT | Carryover and unclassified records are counted separately, not re-certified. |
| Quote | Existing PM Quote Link and PM Data Check | No new Quote ID validation, promotion or amount conversion in this audit. |
| X | Current registry and exact AMEA_X, AMEA_H and H_X agree; H owner and X/H relation are unique | Unique H candidate, conflicting parent or missing registry is review; not proof that every X was discovered. |
| SAM | Exact observed sample row; unique AMEA and X target; only one officially chained X in scope | Shared or ambiguous samples stay in review, no inferred assignment. |
| PO | Direct owner-CSS tracker row with original contract key and timestamp; existing manual-file attestation | H/X-related evidence is related-scope only. Notice, downstream inference, or no tracker row cannot certify PO receipt/missing PO. |
| Mail | Exact project identity, accepted relationship and evidence tier, unique Mail Key | Mail Identity is a derived reference, not a fresh mailbox scan, complete thread, reply status or delivery proof. |
| Invoice | Only board MY_VERIFIED scope; exact current ledger X/AMEA/CMS links and matching CMS sets; compare VAT-gross and known balance when complete | Blank balance stays unknown; amounts and CMS identifiers are not exported. |
| Archive | Existing completion and full-payment attestation, no positive current observed balance, compare auto-receipt snapshot dates and gross | A finding is review of stored evidence, never automatic reopening, payment or delivery certification. |

Global orphan counts identify current X and invoice rows without a board AMEA,
and mail identity rows without a board project. They are not automatically
assigned by customer names. Findings from the independently refreshed tables
may reflect timing differences. Reads are sequential/non-atomic.

## Source freshness

The manifest reports source/snapshot date, mirror sync time, schema and row
count. Check the established Online 48h, Payment 72h/45-day bounds; apply the
same 72h/45-day limit to Prepayments as a **new advisory policy**, not an SLA.
A recent mirror does not make an old dated source recent. Do not re-certify
live source ID/date parity or actual mirror contents from metadata.

SFDC report audit metadata records receipt time and ingest-check time for
Leads, Opportunities and Quotation. The existing 6-hour banner threshold
is used as an advisory receipt-age check (not a report delivery promise).
The stored hash format is checked, but the actual report hash is not
recomputed and the Quote Export timestamp is not inferred. A weekend may
legitimately have no new report.

CSS, Lifecycle, PO Tracker, Mail Identity, X Registry and Quote Export source
freshness remain NOT_ATTESTED in this cross-check. Row Last Sync KST records
last changes, not last successful independent verification; never use it as
a freshness timestamp. Audit start and finish are separate from all source
times. Existing source owners and parity checks remain authoritative.

## Results and operations

### Independent review axes

The 2026-11-24 23:37 KST read-only audit returned 405/405 combined REVIEW
rows, including a shared Quotation report receipt-age warning (approximately
6.6 hours since the scheduled 17:00 report). The warning is advisory; it is
not evidence that a new report is overdue or that all 405 projects are wrong.
Keep the six-hour threshold unchanged until a separate schedule-aware source
contract is approved.

The original `health`, `reasons`, `project_counts` and `reason_counts`
remain conservative combined fields. Use `projection_health`,
`projection_reasons`, `projection_counts` and `projection_reason_counts`
to prioritize individual observed connection/evidence reviews independently
of the shared source metadata. Use `source_metadata_status`,
`source_metadata_reasons` and corresponding aggregate counts for the scoped
advisory source warnings. `review_basis_counts` partitions all board rows
into BOTH, PROJECT_ONLY, SOURCE_METADATA_ONLY, NO_OBSERVED_REVIEW and
NOT_ASSESSED. Carryover/unclassified rows are not newly checked.

A matching archived receipt snapshot with unavailable or stale source
metadata remains a source warning; an observed different snapshot date is
also a project review. The conservative combined archive and invoice review
remain in effect. No receipt, PO, delivery, amount, owner or relationship
decision is changed. A limited projection pass and within-limit metadata
do not establish live source completeness or current project correctness.
All existing unattested-source labels remain visible. Counts can overlap
between diagnostic codes; the review-basis partition cannot.

### Board coverage by owner scope

The post-deployment private native export (2026-11-24 23:30 KST)
reproduced the initial authenticated aggregate: 63/110 current X records
and 192/356 current invoice records had AMEA absent from the Board.
All 63 X records carried OTHER_SALES; all 47 MY_VERIFIED X records were
present on the Board. Among the 192 invoices, 173 were OTHER_SALES and
19 MY_VERIFIED, with 19 distinct AMEA and no exact X assignment.

The additional `board_coverage_by_owner` summary reports separate X and
invoice populations, the existing MY_VERIFIED / OTHER_SALES /
OWNER_UNVERIFIED scope plus UNCLASSIFIED, and fixed-code board/link states.
Invoice registry relation distinguishes no X base observed, absent current
base, one/multiple observed candidates, and explicit X/AMEA disagreement.
An exact X base candidate alone is not exact lineage. All board-absent
counts partition by owner; valid distinct AMEA counts are not additive
across owner groups. Retained records stay excluded. Unknown scope is
not OTHER_SALES. The original unassigned counts are preserved.
No owner, AMEA, invoice, X, balance, receipt, or Board state is changed.
OTHER_SALES is outside the personal queue, not proof of globally correct
coverage. An absent current X may reflect the Online population, not a
missing historical project. Inspect source evidence before repair.

### Combined health labels

- CONFLICT_REVIEW: observed contradiction between projections. Inspect source
  IDs, scope and timestamps before changing business data.
- REVIEW: missing/ambiguous evidence, metadata beyond advisory limits or
  uncertain scope.
- LIMITED_OBSERVED_CHECKS_PASS: limited observed cross-checks agree; missing
  mail/PO/sample observations are explicit domain statuses, not negative proof.
  This is not a health or source completeness certificate.
- NOT_CURRENT_OR_UNCLASSIFIED: board row excluded from current cross-check.

After the stacked PRs are reviewed and deployed, run **Feishu Project
Management Center** on main with mode=health. Only its read-only health job
runs after offline checks. Setup/apply is skipped. There is no additional
cron. Successful execution reports aggregate counts and source metadata in
the run log; it does not declare all projects healthy. Schema, duplicate
keys, incomplete pagination or wrong Base fail closed. Six existing tables
are read once each, with strict metadata validation. The existing 100-row
page size is preserved; Mail Identity uses the same 1,000-page (100,000-row)
ceiling as its existing ingestion owner, while other tables keep the 200-page
(20,000-row) ceiling. Incomplete, oversized or changing catalogs still fail
closed; this is not a guarantee of completeness or live runtime. The two
small metadata ranges are read separately.

In an authorized local environment with existing Feishu and read-only
Google credentials, run:

    python automation/feishu/project_health_check.py --private-report /absolute/private/path/health.json

The optional local report contains AMEA IDs, fixed evidence labels, counts
and review reasons. It does not contain names, subjects, mail bodies,
document references, CMS IDs or monetary values. It must be a new absolute
path outside the repository; creation is exclusive and uses mode 0600 where
the OS supports it. It is refused in CI. Do not upload it to public GitHub
or an unapproved sharing location. Default stdout is aggregate only.

No authenticated production audit was performed in development; PR checks
exercise synthetic fixtures only. Review actual scope, completeness,
metadata and exception volumes before proposing persisted Health fields
or alerts. Future production integration must retain the canonical board's
single writer and avoid frequent rescans of the full mail projection.
