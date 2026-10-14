# Kalman 30th audit — LIVE Vercel Git-link mismatch and frontend P1 net-return guard

Date: 2026-10-15 KST
**VERDICT: AUDIT_CI_PASS / VERCEL_SOURCE_LINK_MISMATCH / PRODUCTION_RELEASE_HOLD**

## 1. Verified read-only Vercel facts (connected tools, not a guess)
- Vercel account/team: `team_eklxTMfdySLBHexmheTiWGCE`.
- Project: `kalman-investment-hub-v2`, project id `prj_KCDIl7qLqtBloI7pjRFQk2Itq7V1`.
- `get_git_deployment_context`: **current project Git connection is `kimtk94/IS_Analysis_V3`**, not Kalman runtime source repository `kimtk94/Codex`.
- `list_deployments(target=production)` and `get_deployment`: ready production deployment `dpl_CYit6nBjGeR4ghkmPHE7ksNKUF68`, Git metadata `kimtk94/IS_Analysis_V3@2615e63e3b3c31014ea75e99b88e81b871f76ba3` (`main`, commit message refers to IS thesis MasterOS).
- `get_deployment` advertised production alias `kalman-investment-hub-v2.vercel.app`. The project has SSO protection on relevant Vercel domains; do not assume public file access.
- GitHub tree of that **specific** `IS_Analysis_V3` commit has 155 paths, none referencing Kalman web `api/assets.js`, `app.js` or the investment hub; metadata discrepancy is real.
- `list_deployment_files` for production returned `404 file_tree_not_found` (twice across audits). The actual deployed `app.js` and runtime API payload remain **UNATTESTED**. Do **NOT** assert live UI definitely renders or hides stale P1 net fields.
- Sanitized proof: `audits/2026-10-15/vercel_link_attestation_snapshot.json` (no credentials or account IDs).

## 2. Known risky consumer source in Codex
- GitHub `kalman-toss-gateway/scripts/build_investment_hub_v7424_execution_telemetry.py` produces a historical `renderExecutionLedger(ctl)` that directly rendered `x.net_return` from `v_live_trade_ledger`, without evidence status.
- The actual Neon `v_live_trade_ledger` view reads historical `metadata.execution_quality.round_trip.net_return` without validation (29th audit).
- Five prior multi-entry managed positions have proven inflated `net_return` at source. The *potential* stale display path in a historical builder is grounded, but deployed JS cannot currently be confirmed.

## 3. GitHub audit-branch-only frontend mitigation
Changed historical builder `build_investment_hub_v7424_execution_telemetry.py`:
- `verifiedNet(x)` yields a numeric net return only if four explicit gates are ALL true:
  - `net_return_evidence_status === 'BROKER_RECONCILED'`
  - `independent_order_manifest_verified === true`
  - `fee_currency_verified === true`
  - `position_fill_coverage_verified === true`
- Missing flags, legacy metadata or `LOCAL_PROVENANCE_ATTESTED` are **NOT** accepted.
- Masked net cell reads **검증 전** and cost basis point field is masked; underlying *price-only gross* return is preserved with clear text saying it excludes costs.
- This patch changes **only a historical source-code generator**. It does not change any compiled/deployed JS, Neon, Vercel Production or runtime API.
- Since current `v_live_trade_ledger` query does not return the four attestation fields, a future generated frontend using this patch would mask **all** net returns until an independently verified data contract is implemented. This is an intended fail-closed design, not a production-ready success.
- Frontend guarding is a presentation safeguard, not proof that another consumer or API cannot use erroneous P1 values.

## 4. Automated Vercel deploy-source mismatch guard
- Pure logic: `audits/2026-10-14/quality/deployment_source_gate.py` consumes a pre-collected sanitized deployment/provenance snapshot, never calls live APIs.
- Rejects wrong project/id, wrong expected/linked/deployed repos, invalid SHA, wrong alias and missing runtime JS attestation.
- **Actual current linked-repo snapshot reliably returns `RELEASE_HOLD/LINKED_REPOSITORY_MISMATCH`.**
- Even a hypothetical fully attested source returns `can_deploy:false` as explicit operator approval is separate.
- This gate is tested in audit CI but **not yet integrated with any production deployment workflow**; it cannot presently prevent an independently triggered Vercel auto-deployment.

## 5. Executed JavaScript/browser-simulation and CI evidence
- `quality/test_investment_hub_net_display.py` invokes the REAL builder's `patch_app` and runs the generated JS `renderExecutionLedger` in a Node.js mock DOM.
- Proven UI rendering behavior for synthetic legacy +198.697% net and -0.212% gross: masked cell displays **검증 전**, gross negative return remains visible.
- Exercises attestation false, local-only status, missing/nonfinite numeric payload and all-gates-present synthetic display (the latter checks the renderer contract, not actual broker truth).
- `quality/test_deployment_source_gate.py`: wrong linked repo, wrong deployment repo, missing runtime, alias and SHA failures, and nonauthorizing positive provenance.
- **GitHub Actions 38644967998 COMPLETED SUCCESS**:
  https://github.com/kimtk94/Codex/actions/runs/38644967998
  - 165 ordinary/offline unittest methods (including the new JS and source tests) PASS
  - 15 synthetic SQLite → disposable PostgreSQL full mirror integration methods PASS
  - **180 test methods total**; the earlier seeded 1,000 arithmetic cases + 2,000 corruptions remain inside 2 test methods.

## 6. REQUIRED next steps before any live fix
1. Independently **attest actual served production HTML/JS/API**, including domain protection, project/root directory and deployment bundle. Do not equate Vercel Git SHA with compiled runtime content if file tree inaccessible.
2. Prepare a **separate operator-approved Vercel Git linkage change** from `kimtk94/IS_Analysis_V3` to the intended Kalman source repository, accounting for existing aliases, build output, runtime env, SSO and rollback. **Do not change during audit.**
3. Establish a durable broker-statement-based `BROKER_RECONCILED` status/manifest and explicit fee denomination. Never derive proof from historical local status alone.
4. Run canary/staging against the active rendering source and API and measure mismatches; obtain user approval before LIVE/Vercel/Neon mutation.
5. Five previously overstated historical net returns in Neon Production **remain unchanged**. All 30th-audit Git changes are confined to `audit/kalman-control-20261014`.

**Decision: P1 PRODUCTION RELEASE HOLD until the repository link, live runtime provenance and independent net-return evidence are resolved.**
