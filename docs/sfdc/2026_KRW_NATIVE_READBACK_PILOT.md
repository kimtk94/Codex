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
