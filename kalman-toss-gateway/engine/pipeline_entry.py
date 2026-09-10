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

    if not os.environ.get('RUN_MODE'):
        raise RuntimeError('RUN_MODE is required')
    runpy.run_module('engine.unified_runner', run_name='__main__')


if __name__ == '__main__':
    main()
