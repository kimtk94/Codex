# NTIS 2021–2026 run on registered outbound IP

The NTIS-approved IP is `182.208.98.218`. GitHub-hosted `ubuntu-latest` is **not** expected to use this IP. NTIS error code 3 was observed from GitHub-hosted runner. The host is currently offline in Remote Desktop Commander, so actual connectivity has not been verified.

## Deployment prerequisites
1. Restore the machine and verify its internet-facing **egress** IP is exactly `182.208.98.218`; inbound IP, DNS name or private IP are not sufficient.
2. Install a trusted GitHub Actions self-hosted runner **on that machine** with labels `self-hosted`, `linux`, `x64`, `ntis`. Use a dedicated least-privilege runner account and current GitHub runner release. Do not run arbitrary untrusted PR jobs on this host.
3. Confirm GitHub Environment `Taehoonserver` has an `NTIS_API_KEY` secret for the approved **국가R&D 과제검색 서비스(전체용)**.
4. In Actions manually trigger `NTIS backfill (approved IP self-hosted)`. Start with 2021–2021 and `max_pages=1` to validate key, XML schema and year filters; a 1-page run may intentionally be flagged incomplete.
5. After API/scheme validation, run 2021–2026 with max_pages sufficient for the data. Inspect `ntis_audit.json`; never interpret an incomplete scan as exhaustive. Topic-keyword collection does not represent all national R&D projects.

The workflow blocks NTIS requests whenever the real public egress IP differs from the approved IP. It neither installs the runner nor changes operating system / router settings. The output is an Actions artifact, **not** a Google Drive or SFDC synchronization.
