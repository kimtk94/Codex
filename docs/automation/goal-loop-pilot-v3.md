# Local AI Goal Loop V3 — synthetic KRW quotation aggregation

## Goal and scope

V2 proved **one** local Qwen → isolated draft PR → exact-head GitHub CI pass.
V3 checks a less trivial Python data-processing task without using private
sales data. This is **not** an SFDC, mail, quote-creation, revenue-sync or
payment automation. Never send external customer data to the model.

The ONLY AI-editable file is
`automation/goal_loop/pilot_quote_summary_v3.py`. The model must implement
`summarize_quotes(rows)`. The goal document, independent acceptance tests,
controller, CI and credentials are not AI-editable.

## Input specification

`rows` is a Python `list` of synthetic quote dictionaries.
A non-list input must raise `ValueError`.
Each valid dictionary requires exactly these fields (extra fields may exist):
`quote_id` (nonempty string after stripping whitespace),
`product_line` (nonempty string after stripping whitespace),
`sample_count` (strictly built-in int >= 1, bool is NOT valid),
`unit_price_krw` (strictly built-in int >= 0, bool is NOT valid).

Reject any invalid row; do not raise for malformed individual records.
Deduplicate `quote_id` after stripping whitespace, case-sensitive.
**Only an accepted row** reserves its ID; later valid duplicates are rejected.

Normalize `product_line` using `.strip().upper()`; group rows by this
product line. For each accepted row add
`sample_count * unit_price_krw`, **VAT-exclusive KRW**, no 10% VAT added.
Zero unit price is valid. Never use float arithmetic or USD prices.
Do not mutate the rows or their dictionaries.

## Exact output

Return exactly three keys:
`{"totals_krw": {"MRNA": 500000, "WGS": 800000},
  "accepted": 3, "rejected": 0}`.
The totals dictionary must be sorted alphabetically by product key.
For an empty list return empty totals and both counts zero.

These totals are entirely synthetic and do **not** represent any real
Novogene quotation or Revenue calculation.

## Independent test and execution boundaries

The independent acceptance module is
`automation.goal_loop.pilot_acceptance_v3`, invoked **only on the
model-authored PR SHA** by GitHub Actions. A model may NOT edit it.
The local V3 static AST preflight checks structure and rejects imports,
module-level code and dangerous calls, **without executing AI code**.
It is not a sandbox or behavioral correctness proof.

Exact SHA-bound GitHub Actions checks required:
`goal-loop-controller-tests`, `pilot-acceptance-v3`,
`main-write-guard`. Only a complete success can yield
`CI_PASS_REVIEW_REQUIRED`. This still requires human review;
NEVER automatically merge or write production SFDC, Feishu, mail,
finance or trading data.

## Budget and history

V3 has its own **new** goal ID `pilot-quote-summary-v3`, immutable goal
hash, separate checkpoint `~/.goal-loop/pilot-quote-summary-v3/latest.json`,
2 attempts per invocation, and maximum 12 recorded attempts cumulatively.
V1 (12/12, failed PR #969) and V2 (3/12, CI PASS draft PR #1007) records
are retained without reset, edits, or automatic merge.

Default installed local model is `qwen25coder3b-16k` on the previously
measured 16 GB Windows laptop. No server dependency. V3 only uses
a compact 4096-context prompt and bounded 1024 generated tokens.
If local Ollama is offline, model creation pauses (HOLD); GitHub Actions
does not pretend to execute the local model.

## Manual single-shot worker invocation

```powershell
cd C:\Users\KimTaeHoon\Projects\Codex
git switch main
git pull --ff-only origin main
python -m automation.goal_loop.controller --goal automation/goal_loop/goals/pilot-quote-v3.json --dry-run
Remove-Item Env:GOAL_LOOP_MODEL -ErrorAction SilentlyContinue
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\automation\goal_loop\windows_worker.ps1" -Goal "automation/goal_loop/goals/pilot-quote-v3.json"
```

Do not add `-Loop` before V3 reaches independent CI PASS.
