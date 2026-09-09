from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from .config import Settings


def main() -> None:
    env_file = Path(os.environ.get('KALMAN_ENV_FILE', '/opt/kalman/.env')).expanduser()
    if env_file.exists():
        load_dotenv(env_file, override=False)
    settings = Settings()
    uvicorn.run('app.main:app', host=settings.host, port=settings.port)


if __name__ == '__main__':
    main()
