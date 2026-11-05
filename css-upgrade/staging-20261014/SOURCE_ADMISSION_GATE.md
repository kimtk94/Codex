# CSS Source Admission Gate (staging only)

Scope: admission policy for a *future* controlled integration test. No production CSS source, DB, credentials, mail, Sheets, or network access is included in this CI job.

- Source remains on the user's authorized server. Do **not** commit, upload, artifact-store, or print the production source.
- The known source SHA-256 is pinned to `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`. A source change must fail closed until reviewed.
- The admission test reads and parses an explicitly supplied local file using AST and verifies a top-level `main`. It never imports or calls the module.
- A synthetic source is used to prove acceptance under a matching hash and rejection of wrong hashes, symlinks, and missing entrypoint.
- Docker keeps `--network none`, `--read-only`, `--cap-drop ALL`, `no-new-privileges`, and bounded tmpfs.
- This is **not** a full CSS E2E test, a guarantee against arbitrary code effects, or authorization to execute the production engine.
- Future controlled execution must use local read-only source and synthetic fixture copies, intercept every DB/Sheets/mail/process sink, prohibit production resource identifiers, assert zero egress, and compare output with a frozen oracle before granting an execution gate.
- No LIVE changes, production secrets, GitHub source transfer, or merge to main.
