# CSS Portfolio Visibility and SIF Action Separation — 2026-10-15

**Release status: STAGING PASS / LIVE NOT DEPLOYED**

## Root cause

The original persistent-Prepayment SIF patch removes SIF-stage Prepayment rows directly from `df_dashboard`, which is later reused to produce the **CSS Project Dashboard, Customer 360, Summary and operational Overview**, not just Action Center and Review Queue. Consequently, false SIF follow-up removal also drops customer-portfolio visibility and undercounts active projects.

## Proposed default (third patch)

**Keep projects visible in the portfolio; suppress only action workflows while SIF is not required.**

| Case | CSS Project Dashboard | Attention | Action Center / Review Queue input | Customer 360 & Summary |
|---|---|---|---|---|
| Active SIF + Prepayment | Visible, stage unchanged | No; `Prepayment - SIF 제출 불필요 (조치 제외)` | Excluded while in SIF stage | Included |
| Active SIF, not Prepayment | Visible | Existing attention rule | Existing workflow | Included |
| Prepayment, progressed to Sample QC | Visible, QC stage unchanged | Existing attention rule | Normal workflow | Included |
| Manual Hold or Skip on Prepayment | Visible | Same SIF suppression | Manual snooze mode preserved | Included |
| No active Prepayment | Visible | Existing attention rule | Unchanged | Included |

The patch snapshots a portfolio dataframe before SIF-only action filtering. It uses the full portfolio dataframe (with SIF attention set to No) to generate Action Center / Review Queue, and the retained portfolio dataframe for Customer 360, Summary, Dashboard sheet, dashboard formatting and Overview.

It also sets `latest_action_required = No` **only for SIF-stage Prepayment rows**, without changing the source timeline or current stage. This is an intentional view-level decision, not a rewrite of the historical email's original request. It does **not** suppress legitimate QC, library, data-ready or non-SIF tasks once the stage advances.

## Evidence

- [1,200 synthetic project portfolio-vs-action workflow regression](https://github.com/kimtk94/Codex/actions/runs/38656873265): **43/43 PASS**. Three real patches applied to server's SHA-verified source copy; AST and Python compile PASS. Verified 1,200 project IDs retained in Dashboard/Customer 360/Summary; only SIF-stage Prepayment removed from Action Center inputs; other attention untouched; QC re-entry; no-Prepayment behavior; triple reverse patch byte-identical. Combined SHA-256: `d675a490007a75c69b7fa408076879e9a52a1078bcc62a32f6fe093da0a32555`.
- [Consolidated 3-patch read-only release preflight](https://github.com/kimtk94/Codex/actions/runs/38656996540): **26/26 PASS**, 433 existing functions preserved, original SHA verified, SQLite `quick_check`/foreign keys PASS, five active durable SIF skips and zero current Overview snoozes. No production source, DB or Sheets writes.
- Previous [1,200-row real Google Sheets writer canary](https://github.com/kimtk94/Codex/actions/runs/38639854155) and [51/51 core SIF workflow checks](https://github.com/kimtk94/Codex/actions/runs/38644452604) remain applicable to the first two patches. The third patch's visual-output contract was verified by executing the actual AST branch and output call sites, **not by running entire CSS main on a live Sheet**.

## Independent Action Center / Review Queue refinement

The portfolio-only third patch initially passed the **filtered** action dataframe to both task generators. Code review showed that this could remove customer metadata or obscure unrelated tasks associated with the same project. A fourth patch routes the **full portfolio frame with SIF attention suppressed** into `build_action_center_output` and `build_review_queue_output`.

The actual Action Center generator creates dashboard-based tasks only for `attention=Yes` rows. It also independently processes unanswered mail, Salesforce inquiries, and manual issues. The fourth patch therefore leaves those independent sources intact while suppressing SIF-stage Prepayment dashboard alerts. The Review Queue retains full project metadata.

- [**51/51 four-patch 1,200-project tests PASS**](https://github.com/kimtk94/Codex/actions/runs/38657405886); validates actual AST call arguments for both builders, fields for independent action sources, visible portfolio vs attention flags, QC recovery, and four-patch exact rollback. Candidate SHA: `851469d0aa53757fd55d5d31357d06068952d3983e79d8ee8b2d15ccb2cbf4fb`.
- [**30/30 four-patch server release preflight PASS**](https://github.com/kimtk94/Codex/actions/runs/38657533752); source identity, 433 functions, syntax, latest SQLite read-only state, all four patches staged and reversed byte-exact. No production deployment.
- Full end-to-end Task Type regeneration with every external mail/CRM/Drive adapter remains untested.

## Implementation artifacts

Apply in order to a separate source copy only:

1. `novogene_sif_history_candidate.patch`
2. `novogene_sif_manual_override_collision.patch`
3. `novogene_sif_portfolio_visibility.patch`
4. `novogene_sif_independent_actions.patch`

Expected original source SHA: `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`

Expected four-patch candidate SHA: `851469d0aa53757fd55d5d31357d06068952d3983e79d8ee8b2d15ccb2cbf4fb`

## Outstanding launch gates

- Production owner acceptance of portfolio-visible/attention-No policy and SIF-only action suppression.
- Full CSS main() end-to-end isolation or approved narrower change-release with single-cycle, next scheduled cycle and source-only rollback.
- Explicit authorization before source replacement or writing the production Google Sheet; Drive backup retention deletions are independent and remain forbidden.

**No live deploy was performed.**
