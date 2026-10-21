# CSS to SFDC source-of-truth migration

Current SFDC_Auto is a Google Sheets snapshot, not a live Salesforce API connection. File modification does not establish row-level freshness.

| Entity | Preferred authoritative source | Current snapshot | Fallback | Promotion gate |
|---|---|---|---|---|
| Account and contacts | SFDC Account / Contact | SFDC_Auto Contact | CSS Customer 360 | Stable ID, LastModifiedDate and verified refresh |
| Opportunities | SFDC Opportunity | SFDC_Auto Oppo list | Email only for contextual exception | OpportunityId and reliable updates |
| Quotations | SFDC Quote | SFDC_Auto Quotation | Quotation Approval List | QuoteId, OpportunityId and dates |
| Quote approvals | SFDC Quote/Approval | Mail-derived approval list | Email pending direct export | Approval outcome and time available |
| Invoice and payment | ERP / SFDC billing if authoritative | SFDC_Auto Issued Invoice filenames | CSS invoice tracking | Structured invoice ID, amount and paid status |
| Settlement | Authoritative finance system | SFDC_Auto Setteled_Rawdata | CSS project ledger | Contract IDs and timestamps validated |
| Activity | SFDC Task/Event/EmailMessage | Email-derived Engagements | CSS Mail Ledger | Direct activity source available |
| QC / data delivery | LIMS and production | CSS project timeline | Email alerts | Do not assume SFDC is authoritative |

Guardrails:
- Preserve existing CSS jobs until completeness, freshness and ID matching are validated.
- Use source provenance and extraction timestamps. Google Drive file modified time is not SFDC record LastModifiedDate.
- Do not automatically reconcile by customer/opportunity names alone.
- Do not overwrite CSS operational ledgers or send customer emails.
- Mirror runs every 30 minutes but cannot refresh its upstream SFDC_Auto snapshot unless upstream automation exists.

Current mirror includes Opportunity, Quotation, SFDC Contacts, SFDC Settlement Raw, SFDC Invoice Index, Quotation Approvals and Quotation Invoice Match.
Next gate: identify SFDC report subscription or approved API for stable IDs and automated export.