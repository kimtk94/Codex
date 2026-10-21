# Feishu Sheets tab discovery
Source spreadsheet: MoZasLAK8hUlsAtIhumjVHjYpQe. The workflow enumerates tabs by stable sheet_id, not by title, every 30 minutes on GitHub Actions (schedule subject to GitHub delays).
Initial discovery emits sheet IDs to the Actions log (never cell content or titles). Inspect and approve those IDs as the baseline before activating change alerts.
No Base table creation or data copying is enabled yet: Sheets read access must pass, and target Base write scopes, column mapping, permissions and idempotency need separate testing. The existing table `표` and `Taehoon` view remain untouched.
If the API returns a permission error, grant the existing Feishu app access to this specific Sheets document and relevant Sheets read scopes.
