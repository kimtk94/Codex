# CSS Vercel deployment policy

This policy is scoped to the Vercel project `css-sales-workspace-git`.
The separately connected Kalman projects are not affected.

- **Production auto-deployment disabled:** `main` is explicitly `false` in `git.deploymentEnabled`. Publishing to Production requires a separate, approved manual release with SHA and authenticated checks; no automatic promotion is created by this config.
- **CSS-oriented Preview only:** only `feat/css-*`, `fix/css-*`, `chore/css-*`, `feat/sfdc-*`, `fix/sfdc-*`, `feat/sales-*`, `fix/sales-*`, `feat/vercel-*`, `fix/vercel-*`, `feat/novogene-*`, and `fix/novogene-*` can trigger Preview deploys. All other branches match the `**: false` rule.
- **Affected build detection:** project-level Vercel settings already enable affected-project detection. An ignored-build step compares `VERCEL_GIT_PREVIOUS_SHA` against HEAD for CSS-root and shared root npm manifest edits. Its exit status causes irrelevant builds to be skipped; it is not guaranteed to prevent an initial Git event or consume zero quota.
- **Source data unchanged:** QQ, Revenue, Feishu, Lead, scheduled Actions and Kalman deployments are outside this policy.
- **Protection unchanged:** do not relax SSO or create bypass links to prove Preview access.

## Release acceptance

A passing CI/offline allowlist test is a policy test, **not** a deployed Preview receipt. A production release remains blocked until the Vercel quota allows a READY Preview for the exact SHA, authorized owner-authenticated browser E2E succeeds, and an explicit release approval is recorded. No publication is initiated by this document.
