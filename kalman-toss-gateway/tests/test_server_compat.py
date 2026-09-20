from __future__ import annotations

import errno
from pathlib import Path

import pytest

from engine import server_compat


def test_rclone_safe_copy2_falls_back_on_eio_under_data_root(tmp_path, monkeypatch):
    root = tmp_path / "drive"
    root.mkdir()
    src = root / "source.txt"
    dst = root / "dest.txt"
    src.write_text("kalman", encoding="utf-8")
    monkeypatch.setenv("KALMAN_DATA_ROOT", str(root))

    def fail_copy2(*_args, **_kwargs):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(server_compat, "_ORIGINAL_COPY2", fail_copy2)
    result = server_compat._rclone_safe_copy2(src, dst)

    assert Path(result) == dst
    assert dst.read_text(encoding="utf-8") == "kalman"


def test_rclone_safe_copy2_does_not_hide_unrelated_eio(tmp_path, monkeypatch):
    root = tmp_path / "drive"
    root.mkdir()
    src = tmp_path / "outside.txt"
    dst = tmp_path / "outside-copy.txt"
    src.write_text("kalman", encoding="utf-8")
    monkeypatch.setenv("KALMAN_DATA_ROOT", str(root))

    def fail_copy2(*_args, **_kwargs):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(server_compat, "_ORIGINAL_COPY2", fail_copy2)

    with pytest.raises(OSError) as exc:
        server_compat._rclone_safe_copy2(src, dst)

    assert exc.value.errno == errno.EIO


def test_local_crypto_xlsx_reads_gspread_style_range(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "Kalman Upbit KRW History 2026-08-22.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Overview"
    ws["A1"] = "Kalman"
    ws["B8"] = "kalman-model-web-v8-hourly-entry-filter"
    ws["A12"] = "Market"
    ws["B12"] = "Last Close"
    ws["A13"] = "KRW-BTC"
    ws["B13"] = 109_867_000
    wb.save(path)
    wb.close()

    values = server_compat._LocalWorksheet(path, "Overview").get("A1:B13")

    assert values[0][0] == "Kalman"
    assert values[7][1] == "kalman-model-web-v8-hourly-entry-filter"
    assert values[12] == ["KRW-BTC", 109_867_000]
