"""Export watchlist.yaml to an Excel sheet for easier editing.

Usage:
    python -m src.watchlist_excel_export --yaml watchlist.yaml \
        --excel watchlist.xlsx

Columns in the generated sheet:
- name
- match_keywords (comma-separated)
- only_half_price (TRUE/FALSE)

Requires: openpyxl, pyyaml
"""
from __future__ import annotations

import argparse
import os
from typing import List

import yaml
from openpyxl import Workbook


def load_watchlist(path: str = "watchlist.yaml") -> List[dict]:
    """Load watchlist YAML into a list of dicts."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        raise ValueError("watchlist.yaml items must be a list")
    return items


def export_watchlist_to_excel(
    yaml_path: str = "watchlist.yaml",
    excel_path: str = "watchlist.xlsx",
    sheet_name: str = "watchlist",
) -> None:
    """Write watchlist entries to an Excel file."""
    items = load_watchlist(yaml_path)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    headers = ["name", "match_keywords", "only_half_price"]
    ws.append(headers)

    for item in items:
        name = item.get("name", "")
        keywords = item.get("match_keywords", [])
        if not isinstance(keywords, list):
            keywords = [str(keywords)]
        keywords_str = ", ".join(str(k) for k in keywords)
        only_half = bool(item.get("only_half_price", False))
        ws.append([name, keywords_str, only_half])

    os.makedirs(os.path.dirname(excel_path) or ".", exist_ok=True)
    wb.save(excel_path)


def main():
    parser = argparse.ArgumentParser(
        description="Export watchlist.yaml to an Excel workbook.",
    )
    parser.add_argument(
        "--yaml",
        default="watchlist.yaml",
        help="Path to watchlist YAML (input).",
    )
    parser.add_argument(
        "--excel",
        default="watchlist.xlsx",
        help="Path to Excel file to write (output).",
    )
    parser.add_argument(
        "--sheet",
        default="watchlist",
        help="Worksheet name to write.",
    )
    args = parser.parse_args()

    export_watchlist_to_excel(
        yaml_path=args.yaml,
        excel_path=args.excel,
        sheet_name=args.sheet,
    )
    print(f"[INFO] Exported {args.yaml} -> {args.excel} ({args.sheet})")


if __name__ == "__main__":
    main()
