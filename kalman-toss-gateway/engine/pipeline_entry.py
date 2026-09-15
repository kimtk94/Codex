from __future__ import annotations

import errno
import os
import runpy
import shutil
from pathlib import Path

from dotenv import load_dotenv


def _install_drive_copy2_compat() -> None:
    """Fallback to content-only copy for rclone/FUSE metadata failures.

    The Colab lineage uses shutil.copy2(), which copies file contents and then
    POSIX metadata/xattrs. rclone/FUSE-backed Google Drive paths can raise EIO
    or ENOTSUP during copystat/listxattr even after the file bytes were copied.
    Keep normal copy2 semantics everywhere else and only relax metadata copying
    when either side is the server's Drive compatibility tree.
    """
    original_copy2 = shutil.copy2
    drive_prefixes = (
        '/content/drive/',
        '/mnt/gdrive/',
    )

    def drive_path(value) -> bool:
        try:
            p = os.path.abspath(os.fspath(value))
        except TypeError:
            return False
        return any(p.startswith(prefix.rstrip('/')) for prefix in drive_prefixes)

    def safe_copy2(src, dst, *, follow_symlinks=True):
        try:
            return original_copy2(
                src,
                dst,
                follow_symlinks=follow_symlinks,
            )
        except OSError as exc:
            recoverable = exc.errno in {
                errno.EIO,
                errno.ENOTSUP,
                getattr(errno, 'EOPNOTSUPP', errno.ENOTSUP),
            }
            if not recoverable or not (drive_path(src) or drive_path(dst)):
                raise

            # copy2() may already have copied the bytes before copystat/xattr
            # failed. Re-copy content only so the destination is deterministic.
            result = shutil.copyfile(
                src,
                dst,
                follow_symlinks=follow_symlinks,
            )
            print(
                '[server] Drive copy2 metadata fallback:',
                os.fspath(src),
                '->',
                os.fspath(dst),
                f'({exc.__class__.__name__}: errno={exc.errno})',
            )
            return result

    shutil.copy2 = safe_copy2


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

    _install_drive_copy2_compat()

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
