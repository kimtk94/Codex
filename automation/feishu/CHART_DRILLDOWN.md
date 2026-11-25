# Feishu chart drill-down and reversible selection (read-only plan)

Requested interaction: click any relevant line point, bar, pie slice or KPI
count; inspect the exact contributing records; select exclusions; see the
remaining count and total; restore exclusions without deleting source rows.
[Feishu's native dashboard guide](https://www.feishu.cn/hc/zh-CN/articles/161059314076-%E4%BD%BF%E7%94%A8%E5%A4%9A%E7%BB%B4%E8%A1%A8%E6%A0%BC%E4%BB%AA%E8%A1%A8%E7%9B%98)
documents click-to-details. Native chart interaction supports filtering
linked charts. Actual permissions, editable drill-down UI, refresh latency
and available API configuration must be tested in this tenant.

## Existing contracts and decisions

| Chart | Source and member | Proposed treatment |
| --- | --- | --- |
| Weekly Quote | Weekly Quote Review / stable quote key | Reuse existing native Active + checkbox filters; do not change source or existing checkbox. |
| Project phase / risk / SIF | Project Progress Board / AMEA | Native member drill-down; separate analysis-only exclusion checkbox and chart copy with all original filters. |
| Payment | Project Progress Board / AMEA | Keep owner/lane/coverage gates. Show project members, then separately reconcile CMS Invoice detail. Never use a project exclusion to mark paid. |
| Monthly Revenue | Monthly Tax Invoice / month (aggregate) | Not invoice-level drill-down. Validate exact members first, then separate review table/analysis chart; keep original official monthly chart. |

A shared checkbox changes a shared dashboard for other editors. Use a
private temporary selection where possible; if using native shared review
checkboxes, make scope and persistence explicit, provide restore and
review audit. No change to formal project or financial status, no delete
or reclassification, no owner-scope change, no propagation across metric
families. Do not turn a manual exclusion into eligibility for a record
excluded by source policy. Selected analysis is not official Revenue.
Show original, excluded, remaining count and known amount, plus number
of unknown amounts. Compute at exact KRW and display conversions only.

## Source observations, 2026-11-25 KST

Connector read of CSS Tax Invoice Extract had 156 distinct admitted
filename/notice/UID invoice references across periods; legacy Revenue
Invoice Base and CSS Tax Invoice List each had 329 distinct invoice
references; 92 overlap Extract. These are not additive populations.
For Oct 2026, the 48 admitted Extract members reproduce published
gross/net/count and canonical authority. For Nov 2026, 40 observed
Extract members vs 37 published, gross/net/count differ and current
Lifecycle also does not match the newer Extract totals. This is a
snapshot difference, not approval to post the extra three. Historical
months are not certified by the current canonical source policy.
No original IMAP/MIME verification or source cutover here.

## Executable plan

dashboard_drilldown_plan.py reproduces the canonical issued-notice
admission, filename check, KST receipt-month and per-invoice VAT rounding
from revenue_net_vat_publish.py, preserves typed references, deduplicates
identical members and fails on contradictory duplicates. Each month
must independently match canonical issued count/gross/net and pass
monthly_revenue_canonical.evidence_rows authority validation. No point is
created for a forecast-only month. Nonmatching months remain blocked.
Only verified months have proposed invoice member payloads in memory;
no row IDs, filenames or money are printed. Legacy overlap is reported
without historical revenue certification.

member_totals supplies original, excluded and selected exact membership
totals with unknown-value counts, using stable keys and refusing unknown
or duplicate keys. review_chart_config returns a prospective native
grouped SUM spec for verified review members with optional exclusion
checkbox. analysis_config preserves existing Board chart policy filters
and adds an analysis checkbox to a copy. These functions are not live
dashboard changes. The review table and analysis checkboxes do not yet
exist by virtue of this code.

## Follow-up: snapshot boundary and review projection plan

Re-read on 2026-11-25: VAT-excluded source verified 2026-11-24 23:25:53
KST, authority 23:25:56. Lifecycle snapshot 2026-11-25 10:35:07 KST
now contains 40 November invoice references with count/gross parity to
the Extract. Filtering Extract by its extraction timestamp <= VAT
snapshot reproduces all three published totals (37 count, gross, net);
receipt-time cutoff instead gives 39 and fails parity. Three additional
members were extracted 2026-11-25 02:28:50–10:33:21 KST; observed
receipt times 2026-11-24 16:02:42 through 2026-11-25 09:57:39 KST.
No AMEA/H/PO filename-field differences in these three; no matching CMS
in the inspected CSS List, legacy Revenue Invoice Base, Outstanding,
eTax or receipt-reference columns. This is evidence of asynchronous
refresh and late extraction, NOT proof of the exact past published
key set, actual payment, or authorization to promote. The preceding
observation that Lifecycle was also behind describes an earlier read.
The 08:59 KST unified run 45514458303 failed Lifecycle at QQ_SOURCE_STALE,
so its dependent monthly job skipped, while Payment passed. Do not
bypass the freshness or canonical authority gates to repair this.

The new snapshot_diagnostics classifies exact current parity, a
timestamp-supported snapshot-lag candidate, or unexplained/incomplete
parity. It does not enable a reconstructed stale month. The proposed
review table has a stable invoice key, exact KRW and count unit,
source references, verification timestamps, and two user-owned
fields (checkbox and reason). review_materialization_plan is a pure
create/update proposal for a dedicated review table, with no delete
or API call. Existing rows and user fields persist; a missing or
changed member, regressing verification time, or blocked month
holds that month and disables current analysis. A future live
implementation must render held-month status or suppress its chart
before allowing any stale data to be mistaken for a current review.
Native views: full, included, excluded; paired original and selected
count/net charts. These configs are proposed, not applied. Actual
click-to-member, edit and restore, permissions and refresh still
require authorized tenant UI verification.

## Deployment gates

1. Run offline tests. Approved merge enables manual main-only read-only
   plan with existing Sheets credentials. No schedule or Feishu API
   credential is added.
2. Recheck published Feishu monthly rows versus the same member source
   revision; reconcile Nov differences; separately verify historical
   invoice membership. Do not replace the official monthly chart.
3. After explicit approval, create or reuse a review-only native table
   with one row per unique invoice and source evidence. Preserve user
   checkbox and exclusion reason on sync. Reconcile original totals to
   official snapshot before enabling editable analysis charts.
4. In native UI test click-to-detail for each point, exact key-set parity,
   exclusion of one and multiple members, unknown values, restoration,
   same-source chart interactions, access control and refresh. Verify
   no operational values changed. Never log member payloads.
