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
    if not os.environ.get('RUN_MODE'):
        raise RuntimeError('RUN_MODE is required')
    runpy.run_module('engine.unified_runner', run_name='__main__')


if __name__ == '__main__':
    main()
