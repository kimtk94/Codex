# Kalman Tool Adoption P0 — Evidence-Based Review

Tracked by #266, PR #267. Scope: read-only repository inspection; no LIVE/Shadow execution changes.

## Evidence (CI artifact from first audit run)
- GitHub Actions run 40204815243: unit tests, read-only inventory and artifact upload successful.
- Artifact: `kalman-tool-adoption-audit.json`; 712 files scanned; one file over 1 MiB skipped.
- Initial detector reported all candidate tools because it scanned its own keyword dictionary and generated manifests. **These are false-positive-prone hints, not evidence of actual installation.**
- P0 follow-up excludes the scanner directory and generated Vercel manifests from content hints; this filter has its own regression test.

## Verified existing features
- `.github/workflows/serverless-harness-smoke.yml`: scheduled 30-minute policy smoke on main, tests, DAG plan export, isolated QC and report, previous artifact quarantine and provenance audit, machine-readable next actions and checkpoint upload.
- `.github/workflows/unified-research-harness.yml`: scheduled research harness every three hours; safety gate, tests, research run and evidence upload.
- `automation_policy/unified_research.py`: explicit IS/CKD research stages; reports MR/coloc/SuSiE/KoGES as **not run** when external verified inputs/executors are not connected.
- `automation_policy/executors.py`: allowlisted deterministic CI QC and report executor; no business executor.

## Incremental adoption decision
| Tool | Existing coverage | Decision |
|---|---|---|
| Codex | GitHub repository, CI and PR workflows already exist | Retain; no new installation |
| ECC / Superpowers | Tests, planning, evidence provenance and safety gates already exist | **Defer installation** until measurable missing workflows are identified |
| n8n | GitHub Actions already schedules jobs and uploads artifacts | Prototype only for external integrations requiring event routing |
| MarkItDown | No verified need in this P0 harness path | Defer |
| Browser Use | Not part of CI harness; potential UI automation | Shadow-only independent security assessment |
| OpenClaw | Potential agent orchestration overlaps existing harness | No production deployment |

## Acceptance gates for any subsequent adoption
1. Concrete functionality not already implemented by CI/Harness.
2. Before/after benchmark for coverage, runtime, failure handling and operating cost.
3. Upstream repository identity, license, releases, and security posture checked separately.
4. Minimal-permission integration, no production secrets, documented rollback.
5. Separate PR with passing targeted tests and maintained evidence artifacts.

## Limitations
This is a file/path scan of the checked-out branch, not an inventory of installed binaries, running services, GitHub secrets, or external accounts. A missing or present keyword cannot establish installation status.
