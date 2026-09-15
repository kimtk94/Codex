from __future__ import annotations

import os
import runpy
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    env_file = Path(os.environ.get('KALMAN_ENV_FILE', '/opt/kalman/.env')).expanduser()
    if env_file.exists():
        # The server-owned .env is authoritative. This prevents stale shell
        # variables from redirecting the Colab compatibility path to old data.
        load_dotenv(env_file, override=True)

    # Preserve compatibility with the original Colab/Alpaca secret names.
    aliases = {
        'APCA_API_KEY_ID': 'ALPACA_API_KEY',
        'APCA_API_SECRET_KEY': 'ALPACA_API_SECRET',
    }
    for legacy_name, server_name in aliases.items():
        if not os.environ.get(legacy_name) and os.environ.get(server_name):
            os.environ[legacy_name] = os.environ[server_name]

    run_mode = os.environ.get('RUN_MODE')
    if not run_mode:
        raise RuntimeError('RUN_MODE is required')

    crypto_source = str(os.environ.get('KALMAN_CRYPTO_SOURCE') or 'rclone_xlsx').strip().lower()
    if run_mode in {'FULL', 'CRYPTO', 'CRYPTO_GLOBAL'} and crypto_source == 'rclone_xlsx':
        from engine.crypto_sheet_file_compat import install_crypto_sheet_file_compat

        path = install_crypto_sheet_file_compat()
        print(f'[server] CRYPTO source: rclone_xlsx ({path})')
    elif run_mode in {'FULL', 'CRYPTO', 'CRYPTO_GLOBAL'} and crypto_source != 'gspread':
        raise RuntimeError(
            "KALMAN_CRYPTO_SOURCE must be 'rclone_xlsx' or 'gspread'"
        )

    runpy.run_module('engine.unified_runner', run_name='__main__')


if __name__ == '__main__':
    main()
