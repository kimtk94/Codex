# Statement issuance-date Forecast (read-only)

Business rule provided 2026-11-25: a sent Statement generally leads to
Tax Invoice after customer confirmation, or automatically around five
days. Treat the Statement lane as stronger billing evidence than a
project-stage estimate, never as already issued revenue or cash.

## Observed evidence

Connector source read: CSS Statement Amount Extract has 29 amount-verified
KRW J+X rows, all 29 exact matches to extracted original Invoice evidence
and amount totals (134,842,400 KRW); 27 were issued within five calendar
days by KST receipt dates and two later. This does not distinguish manual
confirmation from automated issue. CSS Batch Statement Ledger has 29
populated Statement+5d auto-date fields and zero verified confirmation
dates; Confirmation Evidence Ledger 10 rows all awaiting proof.

CSS Git Ingest 12,540 keyed records, 150 original ready/revised notices
(149 distinct exact J+X); 143 match verified Invoice extract. Six exact
X not in current Lifecycle, TAT, or Statement ledger. Of those, one
has original issue notice but missing verified amount (due Nov 17),
three have no issue notice observed and expected dates Nov 18–25,
two have no issue notice observed and expected date Nov 29. All six
lack verified Statement amounts and cannot be added to a monetary
forecast. This is a bounded source observation, not proof of mailbox
completeness or that five invoices are certainly still unissued.
Lifecycle 10:35 KST on Nov 25 reported zero open Statements, current
project estimate 7/21,152,370 KRW Nov, 28/55,235,580 KRW Dec. Source
and projection dates differ. Do not infer personal owner from mailbox.

## Expected-date / identity rule

- Original CSS inbound non-reply INBOX notice with one exact J+X.
  Preserve same-row source ID, first original and latest explicit
  revised notice. Model +5 **calendar days** using KST date. Revision
  reset is an explicit planning assumption, not attested provider SLA.
  Repeated ordinary notices do not move the original estimated date.
- A later verified customer-confirmation proof could move an expected
  issue date earlier, but existing manual proof is absent and this
  audit does not synthesize it. Actual invoice overrides expected date.
- Issue notice without verified attachment amount stays ISSUE_NOTICE_AMOUNT_REVIEW;
  never add it to pending or mark the amount as issued revenue.
- Exact J+X plus filename number/amount, original issued subject, UID
  and zoned date are required to close as verified issue; repeated
  identical invoices deduplicate, conflicting identities fail.
- Verified pending Statement amount needs matching latest notice timestamp,
  UID, UIDVALIDITY, currency and exact J+X. Unknown is not zero.
  Overdue stays in its original due month; separate follow-up state,
  not automatic forward roll. Open J stays visible without a current X row.
- One X may have several J installments. Preserve each and hold its
  original general project estimate once. A statement or issue-review
  event prevents double count; never assume the whole project's
  unbilled residual from a single installment. Already issued J and
  a different open J can coexist. Held estimate is visible but not
  added to the Statement amount. Existing monthly Forecast values
  remain unchanged; report compares them to reconstructed lifecycle
  member counts and amounts.

## Dashboard and operations

Stable private member keys: STATEMENT:J...-X... and PROJECT_FORECAST:X...
allow a future click-to-detail and reversible analysis exclusions, not
source deletion. Show separately actual net revenue, amount-verified
Statement expected (VAT basis unknown), unverified Statement count and
general project forecast (ex-tax estimate); do not add VAT-unknown
Statement KRW to net revenue without explicit tax basis. Owner evidence
must be independently verified before personal KPI publication.
No direct ledger/BI/Feishu writes, actual revenue promotion, mail send,
or recurring workflow. Default output is aggregate, details exist only
in memory. After approved merge, dispatch the main-only read-only audit
and reconcile the six missing source references, recover source amounts
and validate complete source freshness before proposing any production
chart or monthly publication change. Existing original statement and
invoice authority contracts are unchanged.
