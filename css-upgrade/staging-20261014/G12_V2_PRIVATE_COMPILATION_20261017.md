# G12 V2 — private full-source AST compilation, 2026-10-17

**Status: IN-MEMORY COMPILE PASS / STRICT RUNTIME PROTECTION BLOCKED / DEPLOY NOT APPROVED**

## Proven in this step

1. Local zipped V2 candidate independently rerun: **19/19** synthetic tests PASS (receiver single evaluation, a deliberately vulnerable offline negative control, row identity and guard semantics). Original archive is not used as production code.
2. Staged `g12_css_ast_guard_v2.py` and `test_g12_css_ast_guard_v2.py` integrated on `audit/css-g16-boundary-20261016`, with an explicit staging-only test workflow. **52/52** tests PASS: 11 protected field/range tests + 13 fake gspread adapter tests + 12 frozen writer inventory tests + 16 V2 AST guard tests. [CI](https://github.com/kimtk94/Codex/actions/runs/39034492373).
3. Independently, the source-SHA-pinned read-only survey recognized **28/28** of the previously identified AST writer candidates by the V2 matching heuristic, plus **57 dynamic builtin calls** that are not themselves confirmed Sheet writers. [Read-only AST survey](https://github.com/kimtk94/Codex/actions/runs/39034056361). The survey's 28/28 is **NOT** proof of real control-sheet interception.
4. **Actual private CSS source bytes** (SHA-256 `a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840`) were bound read-only into rootless Bubblewrap with isolated network and no home, credentials, live DB or mailbox. The staged V2 transformer parsed and **compiled the entire private CSS module in memory, successfully**, but did not execute the compiled code or import production CSS. [Private SHA-pinned sandbox compile](https://github.com/kimtk94/Codex/actions/runs/39034505538).
5. The **actual V2 transformer**, as distinct from the preliminary 28-call inventory, instrumented **28 calls** and classified **54 further API-style calls as unclassified**:
   - `update`: **45**
   - `sort`: **7**
   - `clear`: **2**
   These may include Python dictionaries and lists; they must NOT all be labeled Sheets writers without source-level target verification.
6. With `reject_unclassified=True`, the V2 transformer **fails closed** on this current source. `strict_unclassified_gate_accepted=false` is expected. The workflow itself is successful because it faithfully reports the deployment-blocking classification, **not** because V2 is approved.

## Risk interpretation

The receiver-once AST fix closes a specific synthetically reproduced time-of-check/time-of-use defect. It does not validate original workbook identity, ownership, exact Sheets API column ranges, physical row/key stability after sort, or cross-system atomic state. Dynamic dispatch (including `getattr`) and indirect adapters may bypass heuristic AST rewriting. Compilation alone is never G12 complete-main execution and is not full G16 sink interception.

The staged `g12_scoped_writer.py` remains a fake in-memory worksheet; none of these tests wrote a real workbook or modified service configurations.

## Next focused work

- Classify the **54 unclassified** API-shaped sites by exact receiver types and source-verified target without exporting proprietary CSS code, private names or values; distinguish innocuous `dict.update` and `list.sort` from genuine Sheets calls.
- Establish a conservative helper-to-worksheet mapping for all 28 instrumented sites, including indirect calls and structural `clear`/`resize`/`set_with_dataframe` routes.
- Replace heuristic guards for operator-input tabs with an actual ownership-separated writer and test both allowed output and operator inputs on a **disposable nonproduction** sheet.
- Test manual edit-after-read and row reorder, failure/retry, lost Sheets response, WAL recovery, all G16 outputs and full G12 main in a genuine disconnected E2E environment.
- Keep PR #168 in DRAFT with explicit release denial until a reviewed rollout/rollback plan and user approval.

**No operational source, live SQLite, Sheets, CRM, mail, schedule or backup configuration was changed.** The private host was used solely for read-only source inspection and temporary sandbox test files under /tmp, cleaned up by the workflow.
