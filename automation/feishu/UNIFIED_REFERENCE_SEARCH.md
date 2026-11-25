# Unified typed reference search (local preview)

This preview is a read-only query module, not a Feishu page, new Registry writer,
or canonical business relationship graph. It can run independently of the #1079
and #1076 drafts; their validated audit output and read hardening remain separate
deployment gates. No scheduled job or credential-bearing CI search is added.

## Scope and use
From an authorized local checkout with the same existing read credentials,
choose an absolute new JSON path in a private, non-synced folder outside Git.
Run the following (example only; choose a real private path locally):
`python automation/feishu/unified_reference_search.py --scope project --type AMEA --output /private/new-search.json`
Enter the identifier at the hidden interactive prompt. Use `--scope all` only
when the existing Feishu/Canonical mail read credentials and all-owner source
access are appropriate. Mail scope can take longer; no partial result is
written if a required source fails. Windows users must ensure the destination's
ACL is private; POSIX creation mode 0600 is not an ACL guarantee. Do not upload
the result to GitHub, public logs, or an unapproved shared folder.

Search exact AMEA, QID, QUOTE_OBJECT, OPP_REF, H, X_PROJECT, X_REPORTED, SAM,
CMS, INVOICE_DOCUMENT_REF, lead/contact/account object references, and exact
mail keys. X and QUOTE are lookup aliases, not identity merges. Finance X
and Lifecycle X stay separate typed values. Salesforce object checksum is
validated; business reference case is preserved for exact QID/Opportunity
lookup. H/X suffixes are not silently shortened. A CMS-labeled mail number,
structured invoice field, document-number and finance CMS number are separate
domains. The current project scope indexes the 20 existing nonmail source tabs,
including existing Registry document references, but not the additional invoice
document sources proposed in #1079. Mail scope indexes Canonical, QQ and CRM
record references; not Mail Identity/tracker relationship assertions. QQ tuple
derived key lookup does not certify a QQ record. CRM keys stay separate.
Message-ID is not a merge key.

Each hit contains the source, read-result ordinal (not stable sheet row ID),
typed observed identifiers and review flags. The direct-edge output is limited
to explicit named column pairs incident to the query; the remaining same-row
references are observations, not inferred edges. Mail rows contribute no
automatic project relationships. Source counts cover all matching rows;
records and direct edges are independently paginated by --offset/--limit,
with remaining counts. Neither the result nor its source observations certify
owner, delivery, payment, issuance, freshness or mailbox completeness.
No search identifiers are included in CI tests, source code commits or stdout.

## Acceptance gates
Offline synthetic tests first. Separate explicit approval before main merge,
then local authenticated read-only test with a small authorized identifier in
each namespace, parity of source record membership, conflict review and
private-output checks. No Feishu UI or business row mutation is authorized by
this preview. A shared UI requires separate owner scope, permission isolation,
stable source-row links and publication review.
