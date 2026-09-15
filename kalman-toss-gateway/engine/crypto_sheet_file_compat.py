from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import types
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from xml.etree import ElementTree as ET

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

DEFAULT_ARCHIVE_BASENAME = "Kalman Upbit KRW History 2026-08-22.xlsx"
EXPECTED_SHEET_KEY = "16stOJy4FmdH9UDSoCppgA9i9VtHsK9WMlu3GauBi0UI"


def _env_file_value(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    return None


def _validate_xlsx(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        with zipfile.ZipFile(path) as zf:
            zf.getinfo("xl/workbook.xml")
    except Exception as exc:
        raise RuntimeError(f"CRYPTO archive is not a readable XLSX file: {path}") from exc
    return path


def resolve_crypto_archive_xlsx(data_root: str | Path | None = None) -> Path:
    explicit = _env_file_value("KALMAN_CRYPTO_ARCHIVE_XLSX")
    if explicit:
        return _validate_xlsx(Path(explicit).expanduser())

    rclone = shutil.which("rclone")
    if not rclone:
        raise RuntimeError("rclone is required for KALMAN_CRYPTO_SOURCE=rclone_xlsx")

    source = (
        _env_file_value("KALMAN_CRYPTO_ARCHIVE_RCLONE_SOURCE")
        or f"gdrive:{DEFAULT_ARCHIVE_BASENAME}"
    )
    config = _env_file_value("KALMAN_RCLONE_CONFIG") or "/etc/rclone/rclone.conf"
    cache = Path(
        _env_file_value("KALMAN_CRYPTO_ARCHIVE_CACHE")
        or "/opt/kalman/state/crypto-archive/Kalman-Upbit-KRW-History.xlsx"
    ).expanduser()
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_name(cache.stem + ".tmp.xlsx")

    cmd = [
        rclone,
        "copyto",
        source,
        str(tmp),
        "--config",
        config,
        "--drive-export-formats=xlsx",
    ]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=int(os.environ.get("KALMAN_CRYPTO_RCLONE_TIMEOUT") or "180"),
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit={proc.returncode}"
        raise RuntimeError(f"rclone CRYPTO archive export failed: {tail}")

    _validate_xlsx(tmp)
    os.replace(tmp, cache)
    return _validate_xlsx(cache)


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n


def _split_cell_ref(ref: str) -> Tuple[int, int]:
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", ref)
    if not m:
        raise ValueError(f"invalid XLSX cell reference: {ref!r}")
    return int(m.group(2)), _col_index(m.group(1))


def _parse_a1_range(a1: str) -> Tuple[int, int, int, int]:
    body = a1.split("!", 1)[-1].replace("$", "")
    if ":" in body:
        left, right = body.split(":", 1)
    else:
        left = right = body
    r1, c1 = _split_cell_ref(left)
    r2, c2 = _split_cell_ref(right)
    return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)


def _shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    out: List[str] = []
    for si in root.findall(f"{{{_MAIN_NS}}}si"):
        parts = [t.text or "" for t in si.iter(f"{{{_MAIN_NS}}}t")]
        out.append("".join(parts))
    return out


def _date_style_indexes(zf: zipfile.ZipFile) -> set[int]:
    try:
        root = ET.fromstring(zf.read("xl/styles.xml"))
    except KeyError:
        return set()

    custom: Dict[int, str] = {}
    num_fmts = root.find(f"{{{_MAIN_NS}}}numFmts")
    if num_fmts is not None:
        for node in num_fmts.findall(f"{{{_MAIN_NS}}}numFmt"):
            try:
                custom[int(node.attrib["numFmtId"])] = node.attrib.get("formatCode", "")
            except Exception:
                pass

    built_in = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))
    out: set[int] = set()
    cell_xfs = root.find(f"{{{_MAIN_NS}}}cellXfs")
    if cell_xfs is None:
        return out

    for idx, xf in enumerate(cell_xfs.findall(f"{{{_MAIN_NS}}}xf")):
        try:
            num_fmt_id = int(xf.attrib.get("numFmtId", "0"))
        except ValueError:
            num_fmt_id = 0
        code = custom.get(num_fmt_id, "")
        simplified = re.sub(r'"[^"]*"|\\.|\[[^]]*\]', "", code).lower()
        looks_date = num_fmt_id in built_in or (
            any(ch in simplified for ch in ("y", "d"))
            and any(ch in simplified for ch in ("m", "h", "s"))
        )
        if looks_date:
            out.add(idx)
    return out


def _excel_datetime(value: float) -> str:
    dt = datetime(1899, 12, 30) + timedelta(days=value)
    if abs(value - int(value)) < 1e-10:
        return dt.strftime("%Y-%m-%d")
    if dt.microsecond:
        return dt.isoformat(sep=" ", timespec="microseconds")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _format_number(text: str) -> str:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    if value.is_integer():
        return str(int(value))
    return format(value, ".15g")


def _sheet_targets(zf: zipfile.ZipFile) -> Dict[str, str]:
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        node.attrib["Id"]: node.attrib["Target"]
        for node in rels.findall(f"{{{_PKG_REL_NS}}}Relationship")
    }

    out: Dict[str, str] = {}
    sheets = wb.find(f"{{{_MAIN_NS}}}sheets")
    if sheets is None:
        return out
    for sheet in sheets.findall(f"{{{_MAIN_NS}}}sheet"):
        name = sheet.attrib["name"]
        rid = sheet.attrib[f"{{{_REL_NS}}}id"]
        target = rel_map[rid].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        out[name] = target
    return out


def _read_sheet(
    zf: zipfile.ZipFile,
    target: str,
    shared: List[str],
    date_styles: set[int],
) -> Dict[Tuple[int, int], str]:
    root = ET.fromstring(zf.read(target))
    values: Dict[Tuple[int, int], str] = {}

    for cell in root.iter(f"{{{_MAIN_NS}}}c"):
        ref = cell.attrib.get("r")
        if not ref:
            continue
        row, col = _split_cell_ref(ref)
        cell_type = cell.attrib.get("t", "")
        try:
            style_idx = int(cell.attrib.get("s", "0"))
        except ValueError:
            style_idx = 0

        if cell_type == "inlineStr":
            is_node = cell.find(f"{{{_MAIN_NS}}}is")
            if is_node is None:
                value = ""
            else:
                value = "".join(t.text or "" for t in is_node.iter(f"{{{_MAIN_NS}}}t"))
        else:
            v = cell.find(f"{{{_MAIN_NS}}}v")
            raw = "" if v is None or v.text is None else v.text
            if cell_type == "s":
                try:
                    value = shared[int(raw)]
                except Exception:
                    value = raw
            elif cell_type == "b":
                value = "TRUE" if raw == "1" else "FALSE"
            elif cell_type in {"str", "e"}:
                value = raw
            elif raw and style_idx in date_styles:
                try:
                    value = _excel_datetime(float(raw))
                except ValueError:
                    value = raw
            else:
                value = _format_number(raw) if raw else ""

        values[(row, col)] = value

    return values


class _Worksheet:
    def __init__(self, values: Dict[Tuple[int, int], str]):
        self._values = values

    def get(self, a1_range: str) -> List[List[str]]:
        r1, c1, r2, c2 = _parse_a1_range(a1_range)
        return [
            [self._values.get((row, col), "") for col in range(c1, c2 + 1)]
            for row in range(r1, r2 + 1)
        ]

    def get_all_values(self) -> List[List[str]]:
        if not self._values:
            return []
        max_row = max(row for row, _ in self._values)
        max_col = max(col for _, col in self._values)
        rows = [
            [self._values.get((row, col), "") for col in range(1, max_col + 1)]
            for row in range(1, max_row + 1)
        ]
        while rows and not any(rows[-1]):
            rows.pop()
        for i, row in enumerate(rows):
            while row and row[-1] == "":
                row.pop()
            rows[i] = row
        return rows


class _Workbook:
    def __init__(self, path: Path):
        self.path = path
        self._sheets: Dict[str, _Worksheet] = {}
        with zipfile.ZipFile(path) as zf:
            shared = _shared_strings(zf)
            date_styles = _date_style_indexes(zf)
            for name, target in _sheet_targets(zf).items():
                self._sheets[name] = _Worksheet(_read_sheet(zf, target, shared, date_styles))

    def worksheet(self, name: str) -> _Worksheet:
        try:
            return self._sheets[name]
        except KeyError as exc:
            raise KeyError(f"worksheet not found in {self.path}: {name}") from exc


class _Client:
    def __init__(self, workbook: _Workbook):
        self._workbook = workbook

    def open_by_key(self, key: str) -> _Workbook:
        if key != EXPECTED_SHEET_KEY:
            raise ValueError(f"unexpected CRYPTO sheet key: {key}")
        return self._workbook


def install_crypto_sheet_file_compat() -> Path:
    path = resolve_crypto_archive_xlsx()
    workbook = _Workbook(path)
    client = _Client(workbook)

    try:
        import gspread  # type: ignore
    except Exception:
        gspread = types.ModuleType("gspread")
        sys.modules["gspread"] = gspread
    gspread.authorize = lambda _credentials: client  # type: ignore[attr-defined]

    try:
        import google.auth  # type: ignore
    except Exception as exc:
        raise RuntimeError("google-auth package is required by the legacy payload import surface") from exc

    google.auth.default = lambda *args, **kwargs: (object(), None)  # type: ignore[attr-defined]

    # A stale server .env may still point at a removed service-account JSON.
    # File compatibility mode must never attempt to use it.
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

    return path
