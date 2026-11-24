# Local AI goal-loop V2 — independent pilot contract

## Relationship to V1

The original `pilot-status-normalizer` goal exhausted its **12/12** bounded
attempts. Its failed [PR #969](https://github.com/kimtk94/Codex/pull/969)
and its Windows checkpoint `~/.goal-loop/pilot-status-normalizer/latest.json`
are immutable historical evidence; do not remove, overwrite, or artificially
reset them. V2 is **a separate goal**, not a successful continuation of V1.

## Objective

Evaluate whether a locally running code model can independently repair a
standalone Python status normalizer using read-only acceptance tests, push an
isolated draft PR and obtain all mandatory CI checks, without running
AI-authored Python locally.

## Editable target

Only `automation/goal_loop/pilot_target_v2.py` is AI-editable.
The `pilot_acceptance_v2.py` tests, static quality gate, controller,
goal documents, CI workflows and secrets are not AI-editable.

## Exact functional contract

The function `normalize_status(value)` must return:

- `PASS`: `pass`, `passed`, `ok`, `done`, `success`
- `FAIL`: `fail`, `failed`, `error`
- `HOLD`: all other values, including unknown text, whitespace,
  empty strings, `None`, numbers, booleans and containers

String input comparison must ignore surrounding whitespace and letter case.

## V2 preflight and independent acceptance

Before the proposed file is written, a purely static Python AST preflight
rejects module-level assertions, expression calls, imports and other code
outside a single `normalize_status(value)` function. This does NOT
prove behavioral correctness or constitute a security sandbox.

Only GitHub Actions runs `python -m unittest
automation.goal_loop.pilot_acceptance_v2 -v` against the AI PR commit
after an independent source quality check. Passing CI for a controller PR
with the V2 acceptance job **skipped** is not V2 goal success.

Completion requires all exact-commit checks:
`goal-loop-controller-tests`, `pilot-acceptance-v2`, and
`main-write-guard`, recorded in `CI_PASS_REVIEW_REQUIRED`.
No automatic merge, deployment, mail, CRM modification or trading.

## Budgets and model evaluation

At most 2 attempts and 35 minutes per invocation, with the controller's
separate 12-attempt cumulative ceiling for **this new V2 goal**. No
automatic retries while the laptop is offline and no background promise.
Default configured model: existing `qwen25coder3b-16k`; optional explicit
`GOAL_LOOP_MODEL=qwen2.5-coder:7b` only when installed and responsive.
The 16GB laptop's historical 3B/4B timings do not establish 7B viability.
Use identical test requirements and compare models using measured
generation latency, CI pass rates, retries and model identity; distinguish
measured results from hypotheses.
