# Kalman Production Security & Operations Backlog

Status: deferred while v7.4.16 focuses on UX/UI.

## P0 — Authentication and exposure boundaries
- Put account/portfolio APIs behind authenticated access.
- Keep broker credentials, Neon writer access, and order execution server-only.
- Minimize public /api/health fields.
- Add CSP, X-Content-Type-Options, frame-ancestors (or X-Frame-Options), and Referrer-Policy.

## P1 — Unified system/data health
- Surface per-market latest snapshot, age, freshness/staleness, coverage, and model version.
- Surface Toss gateway, Neon, Google Drive, and Vercel status.
- Align health-contract semantics with the current annual R5.1 ledger capability.

## P2 — Automated production alerting
Alert on at least:
- US snapshot age > configured freshness threshold.
- Pipeline non-zero exit.
- R5.1 universe coverage below minimum.
- Toss gateway unreachable.
- Account API 5xx.
- Neon writer/publish failure.
- Google Drive mount/read failure.
- Production version/health mismatch.

## Invariants
- Automated trade execution remains separately gated from UI and data refresh.
- Candidate smoke tests and known-good rollback remain mandatory for production promotion.
