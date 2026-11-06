# Salesforce Contact-first Opportunity + Quote Web Intake (Draft)

## Purpose and status

UI prototype at `/sales/oppo-quote`. **No live Contact search, no command
persistence, no Salesforce write or customer mail.** The draft PR is not a
production rollout. The "Save" and "Send" operations remain disabled.

## User workflow

1. Search **only Contacts already linked to an existing Opportunity**, by Korean name (exact match,
   normalized for whitespace; no email- or English-name search in the UI).
2. A trusted CRM backend first filters Contacts by actual Opportunity.Main_Contact__c relationship (Salesforce 006 Opportunity ID). The browser's claimed Opportunity IDs are never proof. Display eligible candidate name and associated **Account institution name**.
   If names collide across institutions, require explicit institution choice.
   If two candidates still share the same institution, HOLD and require
   additional verification. Never assume the first search result is correct.
3. Store the selected **003 Contact ID + 001 Account ID + existing 006 Opportunity ID(s)** tuple in a local
   preview only. Server re-reads Contact and Account from Salesforce, verifies
   both Contact-Account and Opportunity-Contact relationships, checks duplicates and access rights.
   Browser IDs are not trustworthy, even if they look valid.
4. Select service and input sample count and per-sample sequencing depth.
   PE250 PMP depth unit = **M reads**; other sequencing modes = **Gb**.
   Do not infer read-pairs or pricing units without catalog evidence.
5. Prepare a reviewed **Opportunity + Research-AMEA Quote** instruction using
   previously observed same-name naming patterns: Opportunity Name as base;
   Quote Name = Opportunity Name plus the **final AMEA number** after it exists.
6. Check existing Account, Contact, Opportunity, Quote and Quote Product
   identities; do **not** add a duplicate Product. Process and price choices
   must come from a verified service-specific template and catalog.
7. Process Pack is performed only on selected equal-Sample-Number rows whose
   service rules allow packaging; do not lump an unrelated cloud service into
   a pack based on convenience.
8. Present a diff of proposed fields against a grounded reference record.
   **User review** before any future write. No automatic customer emailing.

## Proposed private queue

`DRAFT_LOCAL -> CONTACT_RECHECK_REQUIRED -> WAITING_REVIEW ->
REVIEW_APPROVED -> QUEUED -> UI_FORM_PREPARED -> SAVED_VERIFIED`.

Do not mark a command SAVED_VERIFIED merely because a click succeeded; reload
the Salesforce record and compare exact IDs and fields. On ambiguous matching,
timeout, save error, or orphan Quote, transition to `HOLD` and reconcile.

Each command should have an opaque server-generated ID, authenticated owner,
creation time, expiration, immutable submission snapshot, idempotency key,
versioned schema, audit log and explicit review timestamps. Sensitive customer
data must reside in an authenticated, access-controlled private store, not in
GitHub Actions workflow inputs, logs, build artifacts or public repository files.

## Current implemented validation

- `lib/sfdc-contact-first-command.mjs`: exact Korean name, 003/001 IDs,
  Contact + Account pair, institution disambiguation and no-save command JSON.
- `app/sales/oppo-quote/page.jsx`: Korean-name entry, future institution
  selection control, chosen Contact email read-only, visible no-save status.
- `tests/sfdc-contact-first-command.test.mjs`: synthetic examples only.
- `tests/sfdc-oppo-quote.e2e.mjs`: local Playwright UI, PE250/Gb unit
  switching and zero network write tests in GitHub Actions.

## Unimplemented prerequisites for live use

- Authenticated Salesforce read-only search **restricted to Contacts referenced by actual Opportunity records**, with server-side Contact-Account join and role-based authorization.
- Authenticated private command queue with replay protection and approvals.
- Full field/catalog rules across service types and definitive quote pricing.
- Headless or authorized desktop executor with independently verified IDs and
  post-save readback; browser draft alone is not evidence of a CRM save.
- Final user approval to enable production writes.

**Safety invariant:** no Save, Convert, Save & New, Submit, Send, or new-record
creation in the present prototype. Default to HOLD rather than guess.

## Learning data minimization

Historical Salesforce lists include Contacts without relevant Oppo records. They are **not** training examples or selectable Contacts in this workflow. The private desktop creates a reduced index by reading existing Oppo Main Contact (003) and Account (001) links, then enriching only those linked IDs with Korean name and email. Entries missing a verifiable Oppo association, institution, or valid email go to HOLD. KAIST and Hannam Account cases are SKIP. Do not upload this index to GitHub, Vercel build artifacts, static web assets, or a public spreadsheet. The 412 name-matched single-product Quote-Oppo source examples remain the narrower **template-learning** set; the broader Oppo-linked Contact index is for **customer lookup eligibility** only.
