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
- The pilot confirms one native 2026 Quote; it is **not proof that all 2026 quotes have been extracted**. Expand by verified active + approved records, and crosscheck every Source Quote's Product/process lines before aggregating prices.
