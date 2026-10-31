# CSS Vercel deployment scope

This file documents the staged Vercel Git branch policy in `vercel.json`.

- Automatic Production remains bound to `main` (existing Vercel Git integration). A successful GitHub Actions test is **not** approval to promote Production.
- Preview is allowed only from CSS, SFDC, sales, Vercel maintenance, or Novogene-prefixed feature branches. Research, HCC, Kalman and other unrelated branches should not trigger CSS builds.
- Vercel project-level settings additionally enable affected-project detection and skip builds when the CSS root and its root npm manifests are unchanged. An Ignored Build Step may still create a canceled Vercel deployment entry and consume quota.
- Preview testing must confirm the intended Git SHA, READY state, owner-authenticated access, routes, inbox body UID matching, VAT-exclusive Revenue and manual decision preservation.
- Never disable deployment protection, create a public share link, send customer emails, save SFDC records, or promote Production as part of a read-only scope check.

**Staging boundary:** This branch is for Preview validation only; keep the pull request unmerged until the owner-authenticated Preview E2E and release approval evidence are recorded.
