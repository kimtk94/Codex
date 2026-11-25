# Global data relationship contract — phase 1

## Principle

All source-backed relationships belong to the global data scope, independent
of owner, current Online membership or personal Project Progress Board views.
Missing a Board row is not missing a business identity. Preserve current,
historical, partial and multiple valid relationships. Never manufacture a
relationship to make a dashboard complete. Owner filters are presentation
and action-queue boundaries, not global identity exclusions.

## Existing registry and observed baseline

Read-only source inspection on 2026-11-24 KST (not a transactional snapshot)
found 778 distinct literal AMEA identifiers in the seven core project sources.
CSS Dashboard (404) union CSS Contract-SIF (16) has 405 AMEA; the wider union
adds 373. Timeline (456), Quote Portfolio (517), Lifecycle (111), Outstanding
(303) and eTax (128) are distinct populations; the finance union is 332 and
193 are outside CSS/SIF. These are observed identifiers, not active projects,
confirmed links, or new counts of billable revenue. Online had 110 X and 110
H identifiers. The Quote Export's column named AMEA Quotation ID contained
814 QIDs, not AMEA. Lead report Lead ID is a 00Q object ID while SFDC Lead ID
is the human LEAD reference; report Opportunity ID is an OPP reference, not
a 006 object ID. Do not conflate these domains.

Existing Unified 2025+ Relationships had 315 unique link keys (302
INVOICE->QUOTE, 13 QUOTEAPPROVAL->INVOICE; active not verified), and SFDC
Verified Relations had 828 quote/opportunity reference rows (not revenue).
Reuse these as evidence inputs; their presence does not certify universal
coverage. The raw CRM Opportunity and Quote object tabs were header-only
during inspection. Treat empty or missing fields explicitly.

## Executable source dictionary and scope

See SOURCES, FORMATS, PAIRS and SINGLE_PARENT in
global_relationship_coverage.py. Phase 1 enumerates 20 source tables from
the two existing books: CSS baseline/history/SIF, Quote Portfolio, Lifecycle,
current Online, all four finance mirrors, SFDC mail report staging,
Quote Export, four raw CRM object references and two existing relation
registries. Source role, typed IDs, field presence and same-row reference
edges are counted independently. CRM object IDs retain case and use the
existing 15-character comparison convention. QID, AMEA, X subproject and
invoice-reported X (which may be only a base) remain distinct identity types.
Do not cross-product H and SAM or assign receipt amounts from a grouped CMS
cell. SFDC quote line repeats count as unique observed edges, not duplicate
invoices. Multiple candidate parents are a review signal, not automated
remapping. A second source observation is not independent verification if
both sources derive from the same raw report.

## Evidence levels

| Axis | Interpretation |
| --- | --- |
| Literal key | OBSERVED / EMPTY / FORMAT_REVIEW / PARTIAL_FORMAT_REVIEW |
| Source membership | Source role and snapshot membership; never inferred active/paid |
| Relationship | Observed same-row reference; validated authority stays with existing owners |
| Multiple parents | Review of observed conflicting candidates, no automatic resolution |
| Source freshness | Separate existing manifest / mail receipt / source parity checks |
| Business status | Existing completion, SIF, PO, payment and revenue contracts unchanged |
| Owner | Global coverage unfiltered, owner-specific task views separate |

No new relationship table, source writer, auto-link, record deletion,
financial classification, source promotion or schedule is introduced.
No customer names, ID values, balances or email addresses are logged.
Audit counts are aggregate fixed-field names and codes only. Reads are
sequential, not atomic. Schema absence, oversized grids and incomplete
source sets fail closed; header-only sources are explicit zero observed rows.

## Operation

PR workflow runs offline synthetic tests. Once explicitly approved and
merged, manually dispatch Feishu Global Source Relationship Coverage on main.
The authenticated job uses the existing Sheets read-only credential and
no Feishu write credentials. Existing production writers/schedules are
unchanged. Compare core counts to the baseline above, then use source-field
and multiple-parent counts to prioritize gaps. Do not infer certification
from CI or audit success.

## Phase 2: project-level source reference coverage

Read-only source inspection on 2026-11-25 KST, using the mirror synchronized
08:01 KST, observed 779 core AMEA identifiers and 869 after Prepayments
(90 additional). CSS/SIF baseline 405; expanded outside baseline 464.
Of the 869, 518 had QID references, 457 H, 415 SAM, 111 Lifecycle X,
452 finance-reported X, 498 either direct X reference, 364 CMS references,
309 invoice CMS, 59 prepayment CMS, 29 receipt CMS references. 110 AMEA had
a Lifecycle X literal also observed in current Online; 387 had finance X
references only and one had Lifecycle X not matching current Online.
These are AMEA populations, not counts of invoice, sample, paid or completed
entities. Multiple source membership: 562; single source: 307.
Observed shared H roots (9), CMS references (4), and finance-reported X
references (4) require source review; sharing is not necessarily a conflict
(e.g. cross-quote prepayment). The audit does not auto-merge or remove these.

The added project_relationships function retains each AMEA's direct typed
references, exact source tables, field observation reviews, and missing
AMEA source-row counts. H root and X base matches yield candidates only.
An explicitly suffixed X does not fall back to its siblings. Identical
Lifecycle and Online X identifiers are literal matches only, not proof of
complete H/AMEA/SAM lineage. Receipts are CMS reference observations, not
bank/payment certification; grouped cells remain review evidence.
Optional --private-project-report /absolute/private/new-file.json is a
local-only exclusive file outside the repository (refused in CI).
It contains identifiers and source labels, not customer names, email
contents or amounts; store only in an authorized private location.
Default workflow output is aggregate only. No credentials or write
permissions are added. Canonical mail, full historical invoice sources
and native Feishu record reconciliation still require separate audits.

## Phase 3: mail relationship evidence

The 2026-11-25 connector read inspected the full allocated Canonical Mail
Ledger A:B key range (108,522 grid rows, eleven bounded windows). Actual
keyed rows 53,522, unique keys 53,522, no source-without-key or duplicate
key observed. All Emails legacy 41,005, CSS Git Ingest staging 12,517.
The last keyed row was 53,523. The grid size is not the mail count.
Structured fields R:T and AA over the populated extent returned 22,272
mail rows with valid AMEA (2,061 distinct), 10,599 H (1,077 distinct),
8,607 SAM (1,203 distinct), 22,488 any of those fields, no structured CMS.
Two H cells had unparsed/partial values. Repeated AMEA source reads showed
869 non-mail AMEA, 745 intersection, 1,316 mail-only, 124 non-mail-only,
2,185 union. These are literal source references, not unique real-world
messages, verified delivery, or complete project histories. Structured
invoice field absence does not establish absence of invoice mail.

The new global_mail_relationship_coverage module compares the canonical
ledger with QQ Mail Intake, CRM Filtered Mail Intake, Mail Identity 2026,
Contract PO Tracker and SIF Evidence Tracker. The QQ key is SHA256 of exact
folder|UIDVALIDITY|UID, which can be independently reconstructed from the
canonical staging tuple only. Legacy keys retain their original source
identity; CRM keys are separately namespaced. Message-ID-only matches,
thread links, participant emails, subject identifiers and multi-project
references remain evidence candidates, not automatic assignments. Same
Message-ID across folders is not deletion or deduplication authority.
Structured and subject references are counted separately; suffixes remain
intact, generic numbers are not treated as CMS invoice numbers. Contract,
PO and SIF mail references are checked against their named source, not
treated as file or payment proof.

The manual workflow now accepts scope=project (default) or scope=mail.
Mail runs only on main after offline tests, with existing source credentials,
a GET-only Feishu business API wrapper and read-only Sheets credentials.
It scans the full key/source grid in bounded pages and necessary fields of
the populated keyed extent, verifies keys during payload read and rechecks
grid metadata. This is not a transactional snapshot or a proof that no
unkeyed payload exists beyond the key extent. Feishu pagination is bounded
and strict. No mail bodies/attachments, customer names, IDs or addresses
are exported to logs. No source writes, new table, mail send, recurring
schedule, or source cutover. Live QQ/CRM comparison requires the approved
main dispatch; the prior actual counts came from the Sheets connector.

## Phase 4: previously unmatched mail project reference review

A read-only private backup audit (Feishu 2026-11-24 23:30 KST) observed
31,262 valid QQ Mail keys (one smoke row excluded), 31,260 Mail Identity
keys, two QQ keys absent from Identity and zero Identity keys absent from
QQ. All 1,083 review keys pointed to a QQ row. The existing Identity
projection contained 7,032 PROJECT_ID_EXACT and 2,593 PROJECT_ID_UNMATCHED
rows. The latter cohort, compared with the 869 non-mail AMEA population
on 2026-11-25, comprised 1,092 singleton direct AMEA observations, four
single H-root candidates, 41 partial AMEA references, 36 multiple known
candidates and 1,420 without a non-mail match.

A separate bounded cross-check of the 2,593 grouped backup rows with
the previously observed 53,522 Canonical keyed records (41,005 legacy,
12,517 staging) found:
- 2,503 all explicit AMEA references observed; 58 partial; 14 none;
  18 no explicit AMEA.
- 1,993 AMEA only observed, 568 AMEA and H, 13 H only, 19 neither.
- 1,926 have an AMEA reference also observed in legacy All Emails.
These are literal references, not independently corroborated projects,
and the grouped cross-check could not exclude the same message.

The new unmatched_project_reference_metrics function runs within the
existing read-only mail audit. It partitions existing PROJECT_ID_UNMATCHED
rows by source presence, non-mail candidate state, Canonical literal
AMEA/H observation, legacy membership, H-to-AMEA same-row candidates and
combined source support. It separately reports whether a Canonical
reference comes from another keyed row after excluding the exact QQ
tuple and known equal Message-ID. Even a distinct keyed row is not
proof of distinct real-world mail or authoritative project linkage.
Multiple or partial references are retained; H-root matches remain
candidates, not exact H links. Existing linked rows are not reassigned;
no Identity, source mail, owner, PO/SIF or finance record changes.
Aggregate partition checks and synthetic regression cases ensure
coverage without logging identifiers. Backup/mirror times differ; the
full live Canonical/QQ/CRM crosswalk remains pending authenticated main
audit.

## Remaining phases

1. Run the global source audit and reconcile results to native Feishu
   projection tables, including preserved records and the 19 observed
   owner-scoped outstanding invoices outside Board.
2. Add bounded canonical mail ledger / QQ message identity and evidence
   crosswalk. The Canonical Mail Ledger grid is over 108k rows; do not
   silently truncate or routinely read it in full. Link by immutable
   Mail Key/Message-ID and exact contact/project identifiers; body/name
   candidates stay separate.
3. Audit historical invoice/receipt and legacy 2025 records with explicit
   issue/amount/owner proof. Reuse existing registries and independent
   source authorities; no double counting.
4. Only after verification, propose a shared read-only search/view of all
   entities and related evidence. Reuse existing native Feishu tables where
   sufficient. No new synthetic project rows and no production writes
   without explicit approval.
