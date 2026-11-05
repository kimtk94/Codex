# Salesforce Oppo–Quote local web preview — 2026-11-04

## What runs now

- Windows workstation `NGKR-SAL-TH`, Next.js compiled on the feature branch.
- Loopback-only URL: `http://127.0.0.1:31889/sales/oppo-quote` (only accessible on that PC).
- Korean name lookup is read-only from `~/.sfdc_desktop/web_contact_aliases_PRIVATE.json`, currently 38 approved Contact aliases out of a 48-contact historical sample. The remaining 10 are HOLD.
- Browser name query uses an exact Korean label and a custom header against `/api/sfdc/contact-candidates-local`. HTTP request is same-origin GET, not a Salesforce API call.
- The local API is disabled by default, even if the code is deployed to Vercel. Its enabling environment switch is set only in the local Windows launcher. Requests are rejected unless from an explicitly enabled `127.0.0.1` host with same-origin headers.
- The web UI can also import the private JSON with its file picker, preserving a browser-only fallback.
- After choosing a Contact and editing PMP mode / sample number / depth, the user can download an identity-bound PC review packet. A manual email edit revokes the selected identity. A local desktop validator can compare the packet against the private approved roster and optionally re-check live Salesforce Contact / Account / Opportunity links.

## Start / restart on the authorized PC

Run the checked-in launcher:

```cmd
automation\sfdc_desktop\start_sfdc_local_web.cmd --check
automation\sfdc_desktop\start_sfdc_local_web.cmd
```

Run from the repo root; the launcher resolves its sibling web folder automatically. Prerequisites: `npm.cmd install --no-audit --no-fund` and `npm.cmd run build` in `masteros\web`. It is not a service and does not set a startup task.

## Test observations

- Web unit tests, production Next build and Chromium E2E on the feature branch passed.
- Real PC: local same-origin Contact name lookup returned HTTP 200 and an exact vetted candidate; cross-origin request returned HTTP 403.
- Real private browser test: Korean name lookup -> institution and Contact selection -> identity-bound packet download -> manual email edit invalidates selection. Non-read HTTP requests: zero.
- The downloaded packet independently matched the workstation's approved private roster, and `--live-readonly` confirmed current Contact–Account–Opportunity native links. Prices, product lines, and duplicate Quote checks remain unverified. CRM writes: zero.

## Hosting / limits

The existing `sfdc-oppo-quote-preview` Vercel project is SSO-protected. New Preview creation was attempted but rejected with `api-deployments-free-per-day` (HTTP 402, daily 100 deployments, Retry-After 86,400 seconds). The latest hosted deployment is not guaranteed to contain these changes. No alternate project was created, no Production promotion, and no authentication/security settings changed.

## Future gates

1. Reassess 10 Contact HOLD cases without weakening the ID/email matching criteria.
2. Expand beyond the original 180-Opportunity cohort to all 1,013 in-scope Opportunity records.
3. Create a properly authenticated remote, read-only Salesforce search integration for hosted web. The current PC lookup is a vetted snapshot, not direct live CRM search.
4. Verify current product, price, mandatory Quote fields, and duplicate protections before considering a future approved Save workflow.
