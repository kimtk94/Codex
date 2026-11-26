# Statement full-source recovery (2026-11-25 KST)

Read-only connector evidence: CSS Git Ingest allocated 13,540 rows,
12,540 actual keyed records, 2,541 records beyond the old A1:R10000
read. 149 distinct original Statement keys, 143 exact verified issued
matches; all six remaining latest notices are beyond row 10,000
(and all original notices for those six are beyond the boundary).
One has an original issued notice but no verified filename amount;
five have no original issued notice observed in the staging scope.
No exact J+X matches in the inspected older invoice/Statement review
sources or exact X matches in current Outstanding/eTax. These are
source-snapshot observations, not proof of complete mailbox coverage.

A targeted read of the existing CSS Mail Inbox Raw body cache matched
all seven relevant notices (six Statement + one issue) using exact
INBOX UID, staging folder|UIDVALIDITY|UID Thread Key, Message-ID,
subject, sender, direction, received timestamp and QQ_IMAP_UID_VERIFIED
provenance. Every Statement contained one distinct explicit KRW Total
Amount; candidate pending amounts: Nov 18 one 4,840,000 KRW; Nov 25
two 6,182,000 KRW; Nov 29 two 1,597,750 KRW. Total 5/12,619,750 KRW.
The already-issued-notice Statement was 3,641,000 KRW, excluded from
pending; its actual invoice filename amount remains unknown. VAT basis
and actual current issuance status are not certified by this cache
check. No private keys, subjects, addresses or bodies stored here.

## Correction and recovery gate

The production Statement extractor now reads all allocated source
rows using exact tab/grid metadata, bounded 2,000-row windows,
headers and tuple-key validation, then rechecks grid/header. The
staging, invoice and prior Statement sources use independent bounds.
This is not a transactional snapshot. Do not silently use an issued
notice with no verified filename amount as a new Pending candidate.
A previously verified pending row with such a notice holds publication
for review before writes. Queue reuse requires exact UID, UIDVALIDITY
and timestamp. No change to current production authority, Forecast
calculation, tax basis, original ledger fields or schedule is applied
by the draft.

The original recovery probe uses a read-only Sheets scope and IMAP
readonly SELECT; FETCH only selected original INBOX UIDs, checks
UIDVALIDITY, UID response, sender, exact staged subject and date,
Message-ID and no In-Reply-To. Statement retrieval has a size cap;
MIME bytes remain in memory, no separate attachment save. Only a
single explicit positive integral KRW Total Amount is a candidate.
Issue-only path checks original header plus BODYSTRUCTURE filename
amount, not a substitute Statement total. No message/record changes
or private row logging. Aggregate candidates only; no publication.
The main-only manual probe requires approved merge; PR offline tests
never access credentials. Existing Statement writer is scheduled, so
review automatic execution behavior before approval. Do not merge
until the source gates and original probe are accepted.
