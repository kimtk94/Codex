# QQ 2026 — isolated PostgreSQL hold-only journal

This is the schema contract for a **dedicated** private Neon PostgreSQL
project. It must **never** be installed into the user's investment database.

- There are no invoice numbers, amounts, user emails, Google Sheet IDs,
  real receipt digests, HMAC secrets, connection strings or credentials here.
- Operational data is EMPTY. Validation uses only fake hexadecimal keys and
  fabricated UUIDs on a disposable dev branch or CI PostgreSQL service.
- \`reserve_hold\` inserts one irreversible case claim and one audit event.
  Repeated claims with the same case token are rejected, including a new
  UUID or changed source digest. This is a durable idempotency primitive
  **only within Postgres**, not a global Sheets lock.
- \`mark_uncertain_hold\` records uncertainty at most once. Repeating
  it returns false. No function or valid table state can mark \`VERIFIED\`.
- Audit events reject UPDATE/DELETE via trigger. The **database owner/admin**
  remains privileged and can change schema/triggers; a later execution
  client must use a **separately provisioned least-privilege role**, never
  the owner role. Such a client is not provisioned here.
- Only a future, separately approved authenticated writer could integrate
  this journal with Sheets. PostgreSQL atomicity does not extend to a
  Sheets append/PUT, and other Sheets editors are not excluded.

The CI test starts an isolated PostgreSQL 17 container, applies the versioned
migration, checks deduplication, transition uniqueness and event immutability,
then ROLLBACKs all fake writes and asserts zero rows. No service credentials
or real business writes are required.

**PRODUCTION STATUS: HOLD.** Original QQ 2026 APPLY is hard-blocked,
the private seven-case review is still NOT_REQUESTED 7/7, and no Stage,
Cursor, Canonical Invoice, Revenue, Payment or SFDC writes are enabled.
