#!/usr/bin/env python3
"""Analyze peak concurrently invested capital and ROI from Trade_Journal in an XLSX log."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}


@dataclass
class TradeRecord:
    entry_time: float
    exit_time: float
    order_krw: float
    pnl_krw_est: float


def excel_serial_to_datetime(serial: float) -> datetime:
    return datetime(1899, 12, 30) + timedelta(days=serial)


def col_to_index(cell_ref: str) -> int:
    col = "".join(ch for ch in cell_ref if ch.isalpha())
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def load_sheet_rows(xlsx_path: Path, sheet_name: str) -> list[list[str]]:
    with zipfile.ZipFile(xlsx_path) as zf:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            sst_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sst_root.findall("a:si", NS):
                shared_strings.append("".join(t.text or "" for t in si.findall(".//a:t", NS)))

        workbook_root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels_root.findall("p:Relationship", NS)
        }

        sheet_target = None
        for sheet in workbook_root.findall("a:sheets/a:sheet", NS):
            if sheet.attrib.get("name") == sheet_name:
                rid = sheet.attrib[
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                ]
                sheet_target = f"xl/{rel_map[rid]}"
                break

        if sheet_target is None:
            raise ValueError(f"Sheet not found: {sheet_name}")

        sheet_root = ET.fromstring(zf.read(sheet_target))
        parsed_rows: list[list[str]] = []
        for row in sheet_root.findall("a:sheetData/a:row", NS):
            values_by_col: dict[int, str] = {}
            for cell in row.findall("a:c", NS):
                idx = col_to_index(cell.attrib.get("r", "A1"))
                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", NS)
                if value_node is None:
                    value = ""
                else:
                    raw = value_node.text or ""
                    if cell_type == "s" and raw.isdigit():
                        value = shared_strings[int(raw)]
                    else:
                        value = raw
                values_by_col[idx] = value

            if not values_by_col:
                continue
            max_idx = max(values_by_col)
            parsed_rows.append([values_by_col.get(i, "") for i in range(max_idx + 1)])

        return parsed_rows


def parse_trade_journal(rows: list[list[str]]) -> list[TradeRecord]:
    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    required = ["entry_time", "exit_time", "order_krw", "pnl_krw_est"]
    missing = [c for c in required if c not in idx]
    if missing:
        raise ValueError(f"Missing required columns in Trade_Journal: {missing}")

    records: list[TradeRecord] = []
    for row in rows[1:]:
        try:
            records.append(
                TradeRecord(
                    entry_time=float(row[idx["entry_time"]]),
                    exit_time=float(row[idx["exit_time"]]),
                    order_krw=float(row[idx["order_krw"]]),
                    pnl_krw_est=float(row[idx["pnl_krw_est"]]),
                )
            )
        except (ValueError, IndexError):
            continue
    return records


def calculate_peak_and_roi(records: list[TradeRecord]) -> dict[str, float | int | datetime]:
    events: list[tuple[float, int, float]] = []
    for record in records:
        # type: 0=exit first, 1=entry second (same timestamp overlap 방지)
        events.append((record.exit_time, 0, record.order_krw))
        events.append((record.entry_time, 1, record.order_krw))

    events.sort(key=lambda x: (x[0], x[1]))

    current_invested = 0.0
    max_invested = 0.0
    max_invested_time = 0.0

    for event_time, event_type, amount in events:
        if event_type == 0:
            current_invested -= amount
        else:
            current_invested += amount
            if current_invested > max_invested:
                max_invested = current_invested
                max_invested_time = event_time

    total_pnl = sum(record.pnl_krw_est for record in records)
    total_turnover = sum(record.order_krw for record in records)

    return {
        "trade_count": len(records),
        "max_invested": max_invested,
        "max_invested_time": excel_serial_to_datetime(max_invested_time),
        "total_pnl": total_pnl,
        "total_turnover": total_turnover,
        "roi_vs_peak": (total_pnl / max_invested) if max_invested else 0.0,
        "roi_vs_turnover": (total_pnl / total_turnover) if total_turnover else 0.0,
    }


def format_krw(value: float) -> str:
    return f"{value:,.0f} KRW"


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def build_report(stats: dict[str, float | int | datetime], source_path: Path) -> str:
    max_time = stats["max_invested_time"]
    assert isinstance(max_time, datetime)

    return "\n".join(
        [
            "# Investment Peak & ROI Analysis",
            "",
            f"- Source: `{source_path}`",
            f"- Trades analyzed: {stats['trade_count']:,}",
            "",
            "## 1) 투자금 최대 시점",
            f"- 최대 동시 투자금: {format_krw(float(stats['max_invested']))}",
            f"- 시점(UTC 기준): {max_time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 2) 전체 금액 대비 수익률",
            f"- 누적 손익: {format_krw(float(stats['total_pnl']))}",
            f"- 기준 A (최대 동시 투자금 대비): {format_pct(float(stats['roi_vs_peak']))}",
            f"- 기준 B (전체 회전금액 대비): {format_pct(float(stats['roi_vs_turnover']))}",
            "",
            "## 참고",
            "- 기준 A는 '필요했던 최대 자본 대비 성과'를 보는 지표입니다.",
            "- 기준 B는 전체 주문금액(회전율) 대비 성과를 보는 지표입니다.",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx_path", type=Path)
    parser.add_argument("--output", type=Path, default=Path("investment_peak_report.md"))
    args = parser.parse_args()

    rows = load_sheet_rows(args.xlsx_path, "Trade_Journal")
    records = parse_trade_journal(rows)
    stats = calculate_peak_and_roi(records)
    report = build_report(stats, args.xlsx_path)

    args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
