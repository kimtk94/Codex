# Contract PO follow-up — document receipt verification

This tracker is in the Feishu Sales Base: **Contract PO Tracker**.

## What starts the queue

An original 2026 CSS/CRM notice with an unambiguous project ID and
`Contract Ready/Created` triggers `PO_REQUIRED`. **No Contract notice,
no automatic PO-required row.**

The `PO Status` field is machine-generated from exact-sender source mail.
Do **not** edit it as a substitute for actual document verification.

## How to mark an actual received PO

Open **Contract PO Tracker** and, on that **Project ID** row, set *all four*
manual evidence fields:

| Manual column | Required value |
| --- | --- |
| `PO Document Verification` | `FILE_VERIFIED` (exact string) |
| `PO Document Reference` | A traceable Feishu attachment, file URL, or stable internal file reference |
| `PO Verified At` | Timestamp with timezone, e.g. `2026-11-06T15:00:00+09:00` |
| `PO Verified By` | Name or corporate identity of person who reviewed the actual file |

An incomplete or merely verbal claim is **not** accepted as proof.

The next Contract PO Tracker GitHub Actions sync recalculates
`PO Followup Queue`:
- `PO_REQUIRED`: Contract present and no file attestation or verified receipt notice
- `PO_FILE_REVIEW`: official PO received/approved notice exists but file not yet verified
- `FILE_VERIFIED_ATTESTED`: all four manual fields are present and valid

Only `PO_REQUIRED` appears in the **PO 수령 필요** filtered view. Manually
attested PO records remain in the overall table for audit; they are never
deleted. The machine-generated `PO Status` retains the original mail-only
classification, even when a human has verified the actual file.

## Final Report / Statement downstream evidence (automatic)

Following the business rule, a verified original Final Report or Statement
*notice* that occurs **strictly after Contract creation** is sufficient to
**assume PO was submitted for follow-up purposes**, even if no PO mail exists.
Recognized subjects include `Final Report Ready`, `Final Report Released`,
`Statement Ready`, `Statement Issued` and `Statement Confirmed`.

Only original inbound 2026 CSS/CRM exact-sender mail with a unique project ID
in the subject qualifies. A body-only ID, a forwarded/reply subject, a draft,
request, failure, pending, cancelled, or pre-Contract milestone is excluded.

- `Submission Inference=ASSUMED_BY_DOWNSTREAM_NOTICE`: a downstream milestone
  exists (do not describe this as independently verified PO receipt)
- `Downstream Evidence Type/UTC/Source/Mail Key`: auditable evidence reference
- `PO Followup Queue=PO_SUBMITTED_INFERRED`: excluded from the PO 수령 필요 view
- Later explicit PO missing/request notice after the downstream milestone
  yields `PO_EVIDENCE_CONFLICT_REVIEW` instead of silently closing.
- A direct received PO notification remains `PO_FILE_REVIEW`, and a fully
  manually attested file remains `FILE_VERIFIED_ATTESTED`.
- `PO Status` continues to represent PO-specific mail notices only. An
  inferred submission is never written to the manual proof fields.

## Scope and safeguards

- Original CSS / CRM mail tables, source mailbox, SFDC, and invoice records
  remain read-only.
- Source-only notices do *not* count as actual file verification.
- A manual field is an internal reviewer attestation, not an independent
  cryptographic validation of a signed PDF.
- If one of the four fields is missing, malformed, or unverified,
  the project stays in the follow-up queue.
- Never paste client documents or secrets into GitHub Actions logs.
