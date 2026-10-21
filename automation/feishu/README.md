# Feishu Base integration — P0 read-only

This integration only requests an access token, lists Base tables, and optionally reads one sample record while suppressing its values. It never writes to Feishu.

## Repository secrets

- `FEISHU_APP_ID`: custom app identifier (previously configured in Feishu developer console)
- `FEISHU_APP_SECRET`: application secret, **do not commit**
- `FEISHU_BASE_APP_TOKEN`: Base app token (not wiki node token, not table view ID)
- `FEISHU_TABLE_ID` (optional): actual table ID for a one-record test

The previously shared Feishu wiki URL with `table=wbp...` does not establish the Base app token or table ID. Obtain the app token from the Base's actual URL or API after permissions are granted.

After merging, run Actions > Feishu Base Readonly Probe > Run workflow. The workflow also schedules every 30 minutes on the default branch. If credentials are not set, the workflow fails safely with the missing variable name. Runs do not print secrets or record contents.

If Base access fails: verify Base has shared access with the custom app, the application has Bitable read scopes, and changes are published/approved. No operational sync or external writes are enabled in P0.
