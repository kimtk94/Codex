# 2026 KRW native SFDC Quote Process readback pilot — 2026-11-16

## Confirmed live read-only evidence
- The QQ mail 25-column Quotation Report has `Unit Price USD`, **not** original process-level KRW prices. Never FX convert it for new Quote.
- The authenticated Salesforce `Quotation__c` record **does** display `Currency = KRW`, native `Account 001`, `Contact 003`, Active and full `Quotation Detail` per-Process KRW `Unit Price`.
- A 2026 active, approval-email-matched Quote passed **four process rows** (Extraction/QC, Library, Sequencing, Analysis), each Process Qty × Unit Price = Process Total, and Process totals sum to Quote's VAT-excluded total. The Quote total × 1.10 matched the displayed grand total.
- A second 2026 quote was observed with `Active=False`; it must **never** enter the reusable-price index even if it has Process prices.
- The Quote record page's `Ready to send` state is **not itself proof** of price/quotation approval. The QQ approval email and native Quote ID must be independently cross-checked.

## Read-only local exporter
`automation/sfdc_desktop/quote_2026_krw_browser_export.py` uses **only the user's already-authenticated Chrome** at `127.0.0.1:9222`; it opens and closes an isolated tab without using Edit, Copy or Save.

It requires a **private** manifest containing each approval-matched `2026 QID`, `a0P` record ID, AMEA ID, `APPROVED_TEXT` evidence, created date and Process IDs from the separately SHA256-audited QQ report. The manifest and generated prices **must not be committed** or copied to GitHub Actions logs.

```powershell
python automation/sfdc_desktop/quote_2026_krw_browser_export.py --manifest "$env:LOCALAPPDATA\SFDC_KRW_Price\approval_manifest_private.json" --output "$env:LOCALAPPDATA\SFDC_KRW_Price\2026_krw_process_prices_private.json"
```

- Strict validation: 2026 only, KRW only, Active=True, approved evidence, Account 001 + Contact 003 native links, exact Process ID map, original line totals and VAT.
- A blank source Data Unit is encoded as `NA` and blank Data Size remains blank, **not** invented as 0 Gb. This is common for Extraction/QC or other per-sample steps.
- A `0 KRW` Process may be included in a bundled quotation; **never interpret it as a generally free product**.
- Source `Product fingerprint` uses the visible Product code and ordered Process IDs/types, not the individual Quote Product ID or sample quantity.
- Generated output is a local JSON file for the **browser-only** `/sales/oppo-quote/new` price selector. It is not authoritative approval for the **new** Quote and never changes SFDC prices.
- If any Quote fails source validation, the exporter emits only a non-sensitive HOLD reason and excludes that Quote; no partial reuse from failed quotes.

## Local UI behavior
- Product and Process select from the private file.
- Process Data Unit is selected independently from overall project Gb/reads, so Extraction/QC with no source Data Unit can appear without inventing Gb.
- Candidate priority is same Account + Contact, same Account different Contact, then other customer with exactly matching Product fingerprint, Process ID and Unit.
- All references remain comparison-only pending per-record approval, price recheck and No-Save clearance.

## CI and remaining work
- GitHub Actions run synthetic-only tests of the quote exporter, price selector, source integrity and browser No-Save path.
- GitHub Actions **cannot access the user's logged-in desktop Chrome**; live readback runs locally. Automatic daily parsing of all 2026 Quotes requires a verified private approval manifest and safe rate-limited desktop execution.
- The first pilot confirmed one native 2026 Quote. The extended readback below verifies 20; this is **not proof that all 2026 quotes have been extracted**. Expand by verified active + approved records, and crosscheck every Source Quote's Product/process lines before aggregating prices.

## 2026-11-16 expanded local audit: 20 verified Quotes
- Current QQ Quotation snapshot: received **2026-11-16 17:00:07 KST**; audit status `STAGED_NOT_PROMOTED`; 3,963 process rows and 857 distinct Quote IDs. This report still has USD-converted rate columns, not the original KRW field.
- Screening of the latest approval events: 23 cases considered; 3 excluded before native price export because inactive, multi-Product or inconsistent created date. **20** authenticated, active, approval-evidence-matched 2026 Quotes passed original KRW readback, yielding **78 Process price rows across 16 exact Product fingerprints**.
- Salesforce `Quotation Detail` itself supplied the original KRW Unit Price, Process quantities, price totals and native 001/003 links. Every accepted Quote also satisfied process-sum and VAT checks. **CRM writes: zero**.
- Private merged file on the authorized PC: `%LOCALAPPDATA%\\SFDC_KRW_Price\\2026_krw_process_prices_verified_local.json`. **Never publish this file in GitHub or Actions artifacts.**
- Browser-local price picker accepts all 78 rows, including Process lines with blank Data Unit/Size (`NA`), with 0 rejected.
- Product/process historical table groups by exact Product fingerprint + Process ID + Data Unit + Data Size, showing distinct Quote count, institution count, sample-count range, and min/median/max native KRW Process rates. 0-KRW bundled lines are shown explicitly.
- The **20 Quotes are a recent approved subset**, not the entire 2026 Quote population. Extending this to earlier 2026 approved Quotes requires an incrementally verified private approval manifest and authenticated desktop reads. The current QQ audit's mere SHA presence is not independently rehashed as part of this desktop batch; source line identity is cross-checked against the live Salesforce record before inclusion.

## 2026-11-16 expanded read-only audit (42 Quotes)

- QQ approval evidence audit: 50 approved-text Quote records checked. Existing 20 verified, 30 additional candidates.
- Preflight exclusions: 6 Quotes (4 multi-Product, 1 inactive, 1 source-created-date mismatch). These stay in HOLD; multi-Product quotes need a separate validated Product-aware parser.
- Of 24 single-Product candidates read through authenticated Salesforce, **22 passed**, **2 held** on a mismatch between the displayed VAT-inclusive total and computed total. Prices from both held Quotes were excluded.
- **Final private corpus: 42 verified 2026 Quotes, 164 native KRW Process Unit Price rows, 28 distinct Product fingerprints**.
- Product/Process/Unit/Data Size aggregation yields **119 comparison condition rows**; a condition row is not a distinct customer or new price approval.
- The private local corpus was merged after each batch's verified Quote IDs were confirmed to be disjoint and every row passed original-KRW/Active/approved/001/003/Process/2026 checks. A backup of the earlier 20-Quote corpus was retained.
- Authenticated local URL: `http://127.0.0.1:3002/sales/oppo-quote/new` on NGKR-SAL-TH. Local browser verified HTTP 200, 164/164 rows imported, 28 Product choices, 42 Quotes, 119 price history groups, 0 mutation requests and Salesforce Save disabled.
- Strict limitations: 2026 only, **no USD FX conversion**, comparison-only historic rates, no automatic process price application, no Salesforce writes; local JSON never enters GitHub or GitHub Actions.
- The QQ report audit's lack of a native KRW unit-price column is a **property of that QQ report**, not evidence that authenticated Salesforce Quote Details lack native KRW prices. The two source statuses must remain distinct.
- Remaining future coverage: approved Quote data before 2026-10-19 was not demonstrated complete by this approval-mail shortlist, and 8 held Quotes require separate manual review or a validated multi-Product strategy. This audit does **not** claim that all 2026 Quotes were processed.

## 2026-11-16 follow-up: 8 held quote reinspection and multi-Product readback

Read-only Salesforce Quotation Detail reinspection established:
- **4 multi-Product Quotes** each show exactly two independent Product articles. Each Quote's per-Product line subtotals sum to its displayed KRW net total and the grand total is 110% of net. A new desktop extractor `automation/sfdc_desktop/quote_2026_krw_multi_product_export.py` verifies the **exact source QQ process multiset** (Process ID, name, sample quantity, Data Size/Unit) and per-article Product code, before indexing the rates separately by Product fingerprint.
- The four multi-Product Quotes passed all source, 001/003, 2026 approval, Active, process/total/VAT checks; **33 new original-KRW process rows** added to the local private price corpus.
- Private corpus **46 Quotes, 197 Process rows, 36 exact Product fingerprints, 152 price-history comparison condition groups**, verified on localhost 3002 with HTTP 200, 0 CRM writes, No Save.
- **1 inactive Quote** remains excluded (Salesforce Active=False).
- **1 date discrepancy** remains held: the QQ report source Created Date differs from the date encoded in the QID by one day. The Quote amounts are coherent, but the expected source identity needs a separate explicit policy; no silent correction.
- **2 anomalies remain held**: one 10x Quote displays net/grand 0; one cloud-only Quote displays net 0 yet grand 770,000 KRW. Neither is safe to reuse for standalone approved unit pricing, even if a Salesforce page shows Active=True.
- The QQ 25-column mail report remains USD-priced; historical original-KRW values come exclusively from authenticated Salesforce Quote Detail.
- `/sales/oppo-quote/new` can now accept an explicit **local opportunity-linked Contact readback file**, require user selection of the exact Korean-name and institution Contact, and pass native 001 Account/003 Contact IDs to the KRW comparator. The local evidence is **not** equivalent to a live Salesforce server recheck. Account/Contact edits invalidate the selection.
- All prices continue to be comparison-only. No implicit price inheritance; Salesforce Save remains disabled.

**Private file boundary:** Neither local manifests nor price files with customer identifiers/amounts are committed to GitHub or Actions.

## 2026-11-16 authenticated Contact-to-KRW comparison bridge

- Legacy Feishu quote-contact index inspected locally: 844 quote references, native 003 Contact IDs **0** (last refreshed 2026-11-10). It is not sufficient for same-customer original-KRW price reuse.
- QQ report contains 584 QID-2026 references with Contact/Account names, external `Opp-*` (not native 006), external `CP*` Contact IDs (not native 003), and 15-character Account IDs. Compare native Account IDs using the first 15 characters, without substituting external identifiers.
- Of 46 validated original-KRW Quotes, 43 had a unique Korean name, source email and Account match; 3 held for ambiguous Korean name. These represent 31 distinct Contact IDs and 21 institutions.
- Authenticated Salesforce Quote QID/AMEA, Active, KRW, native 001 Account/003 Contact/006 Opportunity, and live Contact Account/email were rechecked. **30/31 distinct Contacts passed**; one remained held on Account relation verification.
- Private file: `%LOCALAPPDATA%\SFDC_KRW_Price\native_contact_verified_private.json`; never commit or send to GitHub Actions.

### Independent live read-only localhost endpoint

- `POST /api/sfdc/krw-contact-local` requires `SFDC_KRW_CONTACT_READONLY_ENABLED=1`, same-origin 127.0.0.1, `X-SFDC-Command: 1`, Korean name and maximum 10 results.
- **Never set `SFDC_LOCAL_COMMAND_ENABLED=1`** just for customer lookup; that is a separate setting that can enable other CRM command endpoints.
- Searches only the **30 validated 2026 KRW Quote-linked Contacts**, not all Salesforce Contacts. Reopens the already-authenticated local Chrome to recheck Quote/Contact/Account/Opportunity and email on every search, using a new read-only browser tab.
- Index older than 24 hours, uncertain names, multiple unresolved matches, changed native links or invalid Origin all fail closed. No data is fabricated from stale Feishu/QQ contact IDs.
- Operator must explicitly select institution+Contact for homonyms; IDs are carried to historical KRW *comparison only*. No live price auto-application, no new Quote save.
- The existing private local JSON Contact import remains available as a fallback. A zero-result 30-Contact search does **not** mean the customer is absent from Salesforce.
- GitHub Actions run synthetic tests and Next.js browser No-Save checks only; no SFDC credentials, private index, or customer price data are uploaded.

## 2026-11-16 full-year historical expansion pilot: 85 verified Quote references

- Discovered the distinct **Quotation Approvals** source (2026 Jan–Oct) containing **390 separately approved 2026 Quotes**. This is distinct from the recent 50-Quote approval dedup source.
- Crosschecked all 390 QIDs and original Salesforce record IDs against the 2026-11-16 17:00 KST QQ Quotation Report: **333 single-Product, active, consistent-date candidates**; **23 multi-Product** requiring separate article-to-process validation; **26 inactive** (excluded), **8 created-date discrepancies** (HOLD). These are eligibility counts, *not* prices.
- Built private per-category source manifests on the authorized desktop. Sampled four eligible single-Product Quotes per month (Jan–Oct), 40 in total. Authenticated Salesforce browser pass: **39/40 Quotes and 177 original-KRW Process rate rows**, one Quote held because source net/VAT total did not match.
- Reconciled **all 177 lines** against the QQ original Process-ID + Name + Sample Quantity + Data Unit + Data Size multiset; 39/39 Source Quotes passed, zero row rejections. Merged into the previously verified 46-Quote corpus.
- Private local price corpus now: **85 distinct 2026 Quotes, 374 native KRW Process lines, 55 exact Product fingerprints, 250 unique product/process/unit/depth conditions** across Jan–Nov. No USD FX conversions or CRM writes. Existing 46-Quote file was retained as a private backup.
- **Remaining early-year single-Product candidates**: 333 minus 40 attempted = 293 not yet attempted; one of the 40 was held. All 23 older multi-Product candidates need separate authenticated original-article verification. Existing separate recent exceptions remain held: one inactive, two anomalous totals, one created-date discrepancy.
- The recent held Quote with a 2026-11-03 QID has a QQ 2026-11-04 Created Date and AMEA identifier of 2026-11-04; Salesforce view confirms active KRW but does not expose unambiguous creation timestamp in the inspected Details view. Keep it HOLD rather than silently correcting its date.

### Workflow and web improvement

- `automation/sfdc/quote_2026_historical_coverage.py` and synthetic tests enable GitHub Actions to **read the approval source, verify the QQ snapshot SHA256, and report only aggregate eligible/held counts**. CI never sees original KRW process prices or customer IDs.
- New `POST /api/sfdc/krw-price-local` requires independent `SFDC_KRW_PRICE_LOCAL_READ_ENABLED=1`, same-origin 127.0.0.1, a fixed private `%LOCALAPPDATA%` filename, no symlinks, 2MB cap, source age <=24h, and 100% valid source row checks. It is read-only and separate from any SFDC Save/command gate.
- New UI control loads the approved original-KRW file from the authorized PC without manual JSON selection, but retains manual file import as a fallback. All 2026 KRW prices remain **comparison only**.
- Historical price table now paginates **100 condition rows/page**, instead of silently clipping at the first 250 as the dataset grows. Chromium tests use synthetic 260-condition data to verify all three pages and zero SFDC mutation requests.
- Local authenticated Salesforce Contact selection remains limited to the **30 confirmed native 001/003/006 relationships**, requires explicit institution selection, and does not imply that other Salesforce Contacts are absent.

## 2026-11-16 additional authenticated original-KRW readback (123 Quotes, 532 Process rows)

- Source: `Quotation Approvals` has **390** distinct 2026 approved Quote records from Jan–Oct. Exact QQ source matching yields **333** active single-Product eligible cases, plus **23 multi-Product**, **26 inactive**, and **8 source-created-date/QID discrepancy** cases. Eligibility is not evidence of original-KRW price availability.
- The first 40 stratified Jan–Oct cases had **39 PASS / 177 native-KRW Process rows**; one held on Quote Total/VAT mismatch. A second **40 stratified cases** from the same 333-case source had **38 PASS / 158 native-KRW Process rows**; two held on Quote Total/VAT mismatch. All passed cases were checked in authenticated Salesforce Quote Details and reconciled against the exact QQ source Process ID/Name, Product ID, Sample Quantity, Data Unit and Data Size.
- Final current **private** corpus: **123 distinct verified 2026 native-KRW Quotes**, **532 Process Unit Price rows**, **66 Product process fingerprints**, and **303 distinct Product/Process/Unit/Data Size comparison conditions**. The 85-Quote/374-line version is retained at `%LOCALAPPDATA%\SFDC_KRW_Price\2026_krw_process_prices_before_expansion_2_private.json`; current file `%LOCALAPPDATA%\SFDC_KRW_Price\2026_krw_process_prices_verified_local.json`, private audit `2026_krw_expansion2_merged_audit_private.json`.
- Source multiset crosscheck PASS across new 38 Quotes, **zero overlapping Quote IDs, zero rejected line matches, zero CRM writes**. Three VAT/total-mismatch Quotes remain explicitly excluded from the 80-case pilot.
- Historical cohort coverage: **77 of 333** older eligible single-Product Quotes now have authenticated original-KRW pricing; **256** eligible older single-Product Quotes still require original Salesforce reads. The **23 multi-Product, 26 inactive and 8 date-mismatched** older Quotes remain in their separate classification and are not automatically promoted.
- Existing `main` already includes a private, same-origin localhost price read-only route and a **100-row/page pagination** that supports 303+ history conditions; retain these stronger protections rather than introducing a conflicting second pagination implementation.
- The additional UI safety fix clears a chosen reference if customer, Product, Process, Data Unit, requested quantity, production basis, or depth changes. Historical prices remain **comparison-only**, and zero-price steps may reflect bundled pricing. Never convert QQ USD unit prices into KRW.
