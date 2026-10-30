# Kalman Triple Barrier Lab — Vercel workspace

This static web application is scoped to the npm workspace `kalman-triple-barrier-web` and deployed under the `kalman-triple-barrier-lab` Vercel project.

- Deployment root: `research/kalman_triple_barrier/web`
- The CSS Sales Workspace lives independently under `apps/css-sales-workspace`
- Changes to this Kalman web directory must not trigger a CSS Vercel deployment
- GitHub Actions compute, experiments, and source-only directories must not cause both web apps to deploy
- Keep Vercel authorization, domains, secrets, and published Production versions unchanged during scope tests

The web directory is an independent npm workspace with no nested parent workspace.
