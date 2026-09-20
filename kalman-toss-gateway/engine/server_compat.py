from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path
from typing import Any

_ORIGINAL_COPY2 = shutil.copy2
_COPY2_PATCHED = False
_CRYPTO_BRIDGE_PATCHED = False


def _data_root() -> Path:
    return Path(os.environ.get("KALMAN_DATA_ROOT", "/opt/kalman/data")).expanduser().resolve()


def _under_data_root(path: str | os.PathLike[str]) -> bool:
    try:
        Path(path).expanduser().resolve().relative_to(_data_root())
        return True
    except (OSError, ValueError):
        return False


def _rclone_safe_copy2(
    src: str | os.PathLike[str],
    dst: str | os.PathLike[str],
    *,
    follow_symlinks: bool = True,
):
    try:
        return _ORIGINAL_COPY2(src, dst, follow_symlinks=follow_symlinks)
    except OSError as exc:
        # rclone/FUSE may expose file contents normally while listxattr(2)
        # returns EIO. shutil.copy2() copies bytes first, then copystat()
        # probes xattrs. Preserve the file bytes and skip unsupported metadata.
        if exc.errno != errno.EIO or not (
            _under_data_root(src) or _under_data_root(dst)
        ):
            raise
        return shutil.copyfile(src, dst, follow_symlinks=follow_symlinks)


def _install_rclone_copy_compat() -> None:
    global _COPY2_PATCHED
    if _COPY2_PATCHED:
        return
    shutil.copy2 = _rclone_safe_copy2
    _COPY2_PATCHED = True


def _resolve_crypto_xlsx() -> Path | None:
    explicit = os.environ.get("KALMAN_CRYPTO_SHEET_XLSX", "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None

    root = _data_root()
    matches = sorted(
        root.glob("Kalman Upbit KRW History*.xlsx"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


class _LocalWorksheet:
    def __init__(self, workbook_path: Path, title: str):
        self.workbook_path = workbook_path
        self.title = title

    def get(self, range_name: str) -> list[list[Any]]:
        from openpyxl import load_workbook
        from openpyxl.utils.cell import range_boundaries

        min_col, min_row, max_col, max_row = range_boundaries(range_name)
        wb = load_workbook(self.workbook_path, read_only=True, data_only=True)
        try:
            if self.title not in wb.sheetnames:
                raise KeyError(
                    f"Worksheet {self.title!r} not found in {self.workbook_path}"
                )
            ws = wb[self.title]
            rows: list[list[Any]] = []
            for row in ws.iter_rows(
                min_row=min_row,
                max_row=max_row,
                min_col=min_col,
                max_col=max_col,
                values_only=True,
            ):
                rows.append(["" if value is None else value for value in row])
            return rows
        finally:
            wb.close()


class _LocalSpreadsheet:
    def __init__(self, workbook_path: Path):
        self.workbook_path = workbook_path

    def worksheet(self, title: str) -> _LocalWorksheet:
        return _LocalWorksheet(self.workbook_path, title)


class _LocalGspreadClient:
    def __init__(self, workbook_path: Path):
        self.workbook_path = workbook_path

    def open_by_key(self, _spreadsheet_id: str) -> _LocalSpreadsheet:
        return _LocalSpreadsheet(self.workbook_path)


class _LocalCredentials:
    """Sentinel credentials used only by the local-XLSX gspread bridge."""


def _install_crypto_xlsx_bridge() -> None:
    global _CRYPTO_BRIDGE_PATCHED
    if _CRYPTO_BRIDGE_PATCHED:
        return

    run_mode = os.environ.get("RUN_MODE", "").upper()
    if run_mode not in {"CRYPTO", "CRYPTO_GLOBAL", "FULL"}:
        return

    adc = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if adc and Path(adc).expanduser().is_file():
        return

    workbook_path = _resolve_crypto_xlsx()
    if workbook_path is None:
        return

    import google.auth
    import gspread

    def _local_default(*_args, **_kwargs):
        return _LocalCredentials(), None

    def _local_authorize(_credentials, *_args, **_kwargs):
        return _LocalGspreadClient(workbook_path)

    google.auth.default = _local_default
    gspread.authorize = _local_authorize
    _CRYPTO_BRIDGE_PATCHED = True
    print(f"[server] CRYPTO Google Sheet bridge: local XLSX {workbook_path}")


def install_server_runtime_compat() -> None:
    _install_rclone_copy_compat()
    _install_crypto_xlsx_bridge()
