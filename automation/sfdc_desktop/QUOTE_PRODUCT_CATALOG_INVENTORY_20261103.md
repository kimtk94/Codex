# SFDC Quote Product Line catalog inventory (2026-11-03)

## Scope and evidence
Read-only inspection of Salesforce Quotation Detail > Add/Edit on the authorized workstation. The navigator yielded **16 category groups** and **170 service entries**. These are catalog counts, not 170 independently verified Process lists. Raw authenticated Salesforce details remain on the workstation, not GitHub.

| Category | Visible services |
|---|---:|
| AMEA Human RNA Sequencing | 28 |
| AMEA Plant and Animal RNA Sequencing | 32 |
| AMEA Human DNA Sequencing | 13 |
| AMEA Plant and Animal DNA Sequencing | 18 |
| AMEA Pre-made libraries sequencing | 10 |
| Olink | 4 |
| AMEA Microbial DNA Sequencing | 24 |
| AMEA Epigenetics | 24 |
| PTM Proteomics | 1 |
| Quant Proteomics | 3 |
| Untargeted Metabolomics | 3 |
| AMEA Microbial RNA Sequencing | 4 |
| AMEA Life Science Service | 1 |
| Targeted Metabolomics | 1 |
| Spatial transcriptome / RNA product group | 1 |
| AMEA Research-grade virus packaging | 3 |
| **Total** | **170** |

## Detail acquisition protocol
1. Open exactly one Quotation record, choose Quotation Detail > Add/Edit.
2. Expand each category, identify the exact service row, click its specific + button.
3. Enter Sample Number if enabled and Data Size only if enabled; otherwise record a skipped field.
4. Click Next, wait for the Process List and collect process types and candidates.
5. Close the working tab without clicking Done or Save. Do not create a Product, Quote Product, or change customer prices.
6. Checkpoint each result by unique category and service; retry transient loading errors without claiming PASS before Process List readback.

## Verification
- Authenticated UI collection runs on the owner's authorized Windows workstation only.
- GitHub Actions runs synthetic tests of catalog_inventory_contract.py without customer data, Salesforce credentials or live UI access.
- Process candidates are not automatically required/default Process selections. Product IDs, unit rules and pricing require separate validation.
- Refresh the category/service count before claiming 100% coverage because the live Salesforce catalog may change.
