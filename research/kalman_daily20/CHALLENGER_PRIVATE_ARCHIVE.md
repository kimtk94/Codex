# Challenger private historical archive worker (research only)

This CLI is separate from the public GitHub Actions runner. It is not a
prospective publisher and must not be scheduled or activated until reviewed.
The public CI exercises only fake provider behavior and credential-free
verification of actual historical artifacts.

## Private prerequisites

- A trusted single Linux worker and durable owner-only state directory (0700).
- A dedicated Google OAuth **authorized user** credential for the Taehoon
  account, scoped only to `https://www.googleapis.com/auth/drive.file`.
  User consent and app/file selection are required; existing connector tokens
  are not exportable to this process. Do not use the existing Daily20 service
  account or place OAuth secrets in this public repository or PR jobs.
- Grant this app access to the existing private research folder via a supported
  file selection/authorization flow. The worker checks the authorized account
  permission ID and email, exact folder ID and parent, owner-only permissions,
  private visibility, and create capability. Store these expected values in a
  privately provisioned JSON config (0600) with keys `account_label` (Taehoon),
  `account_email`, `account_permission_id`, `folder_id`, `parent_id`. Pin its
  SHA256 independently. Do not commit the config or the credential file.
- Set `CHALLENGER_DRIVE_OAUTH_FILE` privately to the authorized-user JSON path
  (0600, explicit scope list and type). Install google-auth and
  google-api-python-client in the reviewed private runtime.

## Invocation and review

Obtain the completed Actions run's two ZIPs and their SHA256 values through
the authenticated GitHub API, separately from the handoff JSON. Review and pin
the expected run and head commit. Run `challenger_private_archive_worker.py`
with `--verify-inputs-only` first; supply `--handoff`, `--handoff-sha256`,
`--rehearsal`, `--rehearsal-sha256`, `--run`, and `--commit`.

For the private credentialed invocation also supply `--config`,
`--config-sha256` and `--state-dir`. Default `--mode plan` performs no creates.
Only a reviewed private operator should choose `--mode archive`. No actual
OAuth credential or worker is provisioned by this PR.

A new name includes the run ID and full SHA256 in a worker-specific namespace.
Existing app-visible exact-name copies are reused only after full byte and
metadata readback. The worker persists a preallocated Drive ID before creating
a new file; retry uses the same ID and verifies conflicts, never overwrites
files. Local state and exclusive lock must persist across restarts. Retain
private receipts; do not publish them as public artifacts.

Drive.file access may not enumerate files the app has not been granted access
to. Name uniqueness is not a cross-client guarantee. Do not run another writer
in the same namespace or reset state to work around conflicts. Existing manual
archives are not migrated or modified. Multi-file creation is not atomic;
partial success can be resumed. Owners can still edit/delete the files; these
receipts do not certify immutable storage or prospective timestamps. No
independent market price certification or LIVE approval is implied.

References:
- https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- https://developers.google.com/workspace/drive/api/guides/manage-uploads
