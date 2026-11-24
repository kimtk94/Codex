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
