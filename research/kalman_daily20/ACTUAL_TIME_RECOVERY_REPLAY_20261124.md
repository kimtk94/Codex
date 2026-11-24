# Nov 23 actual-time recovery: independent replay acceptance

Research only. No trading or source-finality promotion. #1045 remains open.

## Original capture evidence

- Original run: [45382109010](https://github.com/kimtk94/Codex/actions/runs/45382109010), `workflow_dispatch`, code SHA `06c66c0fea6de93eeb581ce856d648d24c0ff942`.
- XNYS session 2026-11-23; actual first capture on 2026-11-24 at about 11:15 UTC, before the next regular open at 14:30 UTC. No scheduled-slot credit.
- First capture new events: 20 Bull + 40 Bear. Total journals: 40 Bull + 80 Bear (including the legacy Nov 20 events); settled 0.
- Original snapshot SHA256: `1d054e08d38a00f4c46371d3f11921310ea26b34262a98972192e416f4187d7f`.
- Bull journal SHA256: `86c4e2175235bc95d965e5e908df36e9b64b848e8ebf0b14042f95bb0bd2a7d9`.
- Bear journal SHA256: `375ed264c246e43355179ab7904535ac09c48b0836b498412853c6fd93f8f12e`.
- [Versioned results archive](https://drive.google.com/file/d/1ExY3SRG5UzLFSd9_j4i9vqntmKf1yLYQ/view), SHA256 `256467e4ed8d3979c1f8c28993f9aed1fb7f4f16135879d1809b870456c8622f`.
- [Versioned data archive](https://drive.google.com/file/d/1hH1qe7Ino8IOS7DEmEkeY_RpHxrdmx2p/view), SHA256 `e8fe9d37e3db3037280878adf63bd0e0e51dd2ca3ca71ebb2dfbdefe86897711`.
- Both versioned archives downloaded independently and compared byte-for-byte by SHA256 against their captured canonical counterparts; exact matches.

## Replay request and acceptance

This documentation-only change triggers the existing reviewed main-push Daily20 path, with a distinct Actions run ID and a docs-only commit SHA. It changes no executable code, model weights, provider data, scheduling, credentials, signal policy, or deployment.

The protected first-seal gate already rejects main-push attempts to create a new original seal. For this experiment require:

1. Independently restored prior ZIP contains the original run 45382109010 and the Nov 23 complete frozen cohort.
2. Replay still targets 2026-11-23, mode SAME_SESSION_REPLAY_EXPECTED; prior original snapshot preserved byte-for-byte.
3. Zero added Bull and Bear signals, no rewritten original events; no outcome has matured yet.
4. Compare actual recomputed inputs and scores, separately from immutable archive preservation. Any drift is HOLD, not proof of reproducibility.
5. Verify remote results readback, exact original run ID and snapshot SHA; independently compare downloaded results archive with both saved journal hashes.
6. Retain all official-price/source-finality and scientific/LIVE HOLDs. This non-scheduled replay is not evidence of native cron restoration and must not count as either scheduled slot.

No claim of replay success until the actual new run is inspected.
