from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from engine.crypto_sheet_file_compat import (
    _Workbook,
    resolve_crypto_archive_xlsx,
)


def _sheet_xml(rows: list[list[tuple[str, str]]]) -> str:
    body = []
    for r_idx, row in enumerate(rows, start=1):
        cells = []
        for c_idx, (kind, value) in enumerate(row, start=1):
            n = c_idx
            letters = ""
            while n:
                n, rem = divmod(n - 1, 26)
                letters = chr(65 + rem) + letters
            ref = f"{letters}{r_idx}"
            if kind == "s":
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
                )
            else:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        body.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(body)}</sheetData></worksheet>'
    )


def _write_test_xlsx(path: Path) -> None:
    overview_rows = [
        [("s", "")],
        [("s", "")],
        [("s", "")],
        [("s", "")],
        [("s", "")],
        [("s", "")],
        [("s", "")],
        [("s", "Model"), ("s", "web-v8-test")],
        [("s", "")],
        [("s", "")],
        [("s", "")],
        [
            ("s", "Market"),
            ("s", "Last Close"),
            ("s", "Last Candle (KST)"),
            ("s", "Watch Signal"),
            ("s", "Model Signal"),
            ("s", "Regime"),
        ],
        [
            ("s", "KRW-BTC"),
            ("n", "100000000"),
            ("s", "2026-09-15 20:00:00"),
            ("s", "WATCH"),
            ("s", "HOLD"),
            ("s", "NEUTRAL"),
        ],
        [
            ("s", "KRW-ETH"),
            ("n", "5000000"),
            ("s", "2026-09-15 20:00:00"),
            ("s", "WATCH"),
            ("s", "HOLD"),
            ("s", "NEUTRAL"),
        ],
    ]
    candle_rows = [
        [("s", "timestamp"), ("s", "open"), ("s", "high"), ("s", "low"), ("s", "close")],
        [("s", "2026-09-15 16:00:00"), ("n", "1"), ("n", "2"), ("n", "0.5"), ("n", "1.5")],
        [("s", "2026-09-15 20:00:00"), ("n", "1.5"), ("n", "2.5"), ("n", "1"), ("n", "2")],
    ]

    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Overview" sheetId="1" r:id="rId1"/>
    <sheet name="KRW_BTC_4H" sheetId="2" r:id="rId2"/>
    <sheet name="KRW_ETH_4H" sheetId="3" r:id="rId3"/>
  </sheets>
</workbook>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>
</Relationships>"""
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cellXfs count="1"><xf numFmtId="0"/></cellXfs>
</styleSheet>"""

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", rels)
        zf.writestr("xl/styles.xml", styles)
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(overview_rows))
        zf.writestr("xl/worksheets/sheet2.xml", _sheet_xml(candle_rows))
        zf.writestr("xl/worksheets/sheet3.xml", _sheet_xml(candle_rows))


class CryptoSheetFileCompatTests(unittest.TestCase):
    def test_workbook_matches_legacy_gspread_surface(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "archive.xlsx"
            _write_test_xlsx(path)

            book = _Workbook(path)
            overview = book.worksheet("Overview").get("A1:Z30")
            self.assertEqual(overview[7][1], "web-v8-test")
            self.assertEqual(overview[11][0], "Market")
            self.assertEqual(overview[12][0], "KRW-BTC")
            self.assertEqual(overview[12][1], "100000000")

            btc = book.worksheet("KRW_BTC_4H").get_all_values()
            self.assertEqual(btc[0][:5], ["timestamp", "open", "high", "low", "close"])
            self.assertEqual(btc[-1][0], "2026-09-15 20:00:00")
            self.assertEqual(btc[-1][4], "2")

    def test_explicit_archive_path_wins(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "custom.xlsx"
            _write_test_xlsx(path)
            with patch.dict(
                os.environ,
                {
                    "KALMAN_CRYPTO_ARCHIVE_XLSX": str(path),
                    "KALMAN_DATA_ROOT": "/does/not/matter",
                },
                clear=False,
            ):
                self.assertEqual(resolve_crypto_archive_xlsx(), path)


    def test_rclone_archive_export_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = root / "cache.xlsx"

            def fake_run(cmd, **kwargs):
                tmp = Path(cmd[cmd.index("copyto") + 2])
                _write_test_xlsx(tmp)

                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = ""

                return Result()

            env = {
                "KALMAN_CRYPTO_ARCHIVE_CACHE": str(cache),
                "KALMAN_CRYPTO_ARCHIVE_RCLONE_SOURCE": "gdrive:archive.xlsx",
                "KALMAN_RCLONE_CONFIG": str(root / "rclone.conf"),
            }
            with patch.dict(os.environ, env, clear=False), \
                 patch("engine.crypto_sheet_file_compat.shutil.which", return_value="/usr/bin/rclone"), \
                 patch("engine.crypto_sheet_file_compat.subprocess.run", side_effect=fake_run):
                result = resolve_crypto_archive_xlsx()

            self.assertEqual(result, cache)
            self.assertTrue(result.is_file())
            self.assertEqual(
                _Workbook(result).worksheet("KRW_BTC_4H").get_all_values()[-1][4],
                "2",
            )


if __name__ == "__main__":
    unittest.main()
