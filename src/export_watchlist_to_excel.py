"""Export watchlist.yaml to an Excel sheet for easier editing.

Usage:
    python -m src.export_watchlist_to_excel --yaml watchlist.yaml \
        --excel watchlist.xlsx

Columns in the generated sheet:
- name
- match_keywords (comma-separated)
- include_keywords (optional; comma-separated final inclusion filter)
- exclude_keywords (comma-separated)
- stores (comma-separated; Coles/Woolworths/none)
- email_indices (optional; comma-separated zero-based recipient indices)
- price_range (optional; e.g. 1-1.5 or <1.50)
- size_range (optional; e.g. 800-1000 or 900)
- include_unknown_half_price (TRUE/FALSE)
- only_half_price (TRUE/FALSE)

Requires: openpyxl, pyyaml
"""

from __future__ import annotations

import argparse
import csv
import os
from io import StringIO
from typing import List

import yaml
from openpyxl import Workbook


def load_watchlist(path: str = "watchlist.yaml") -> List[dict]:
    """Load watchlist YAML into a list of dicts."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"YAML file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        raise ValueError("watchlist.yaml items must be a list")
    return items


def _join_keywords(keywords: object) -> str:
    """Serialize keywords so commas inside a keyword round-trip safely."""
    if isinstance(keywords, list):
        values = [str(keyword) for keyword in keywords]
    elif keywords in (None, ""):
        values = []
    else:
        values = [str(keywords)]

    buffer = StringIO()
    csv.writer(buffer).writerow(values)
    return buffer.getvalue().strip("\r\n")


def _optional_csv_field(item: dict, key: str) -> str | None:
    """Return a CSV-style field only when the source key is explicitly present."""
    if key not in item:
        return None
    value = item.get(key)
    if isinstance(value, list) and not value:
        return "[]"
    return _join_keywords(value)


def _optional_bool_field(item: dict, key: str) -> bool | None:
    """Return a boolean field only when the source key is explicitly present."""
    if key not in item:
        return None
    return bool(item.get(key))


def _optional_text_field(item: dict, key: str) -> str | None:
    """Return a trimmed text field only when the source key is explicitly present."""
    if key not in item:
        return None
    value = item.get(key)
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _optional_email_indices_field(item: dict) -> str | None:
    """Return normalized email indices from either YAML key shape."""
    if "email_indices" in item:
        return _join_keywords(item.get("email_indices"))
    if "email_index" in item:
        return _join_keywords(item.get("email_index"))
    return None


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

    headers = [
        "name",
        "match_keywords",
        "include_keywords",
        "exclude_keywords",
        "stores",
        "email_indices",
        "price_range",
        "size_range",
        "include_unknown_half_price",
        "only_half_price",
    ]
    ws.append(headers)

    for item in items:
        name = item.get("name", "")
        keywords_str = _join_keywords(item.get("match_keywords", []))
        include_keywords_str = _optional_csv_field(item, "include_keywords")
        exclude_keywords_str = _optional_csv_field(item, "exclude_keywords")
        stores_str = _optional_csv_field(item, "stores")
        email_indices_str = _optional_email_indices_field(item)
        price_range = _optional_text_field(item, "price_range")
        size_range = _optional_text_field(item, "size_range")
        include_unknown_half_price = _optional_bool_field(
            item,
            "include_unknown_half_price",
        )
        only_half = _optional_bool_field(item, "only_half_price")
        ws.append(
            [
                name,
                keywords_str,
                include_keywords_str,
                exclude_keywords_str,
                stores_str,
                email_indices_str,
                price_range,
                size_range,
                include_unknown_half_price,
                only_half,
            ]
        )

    os.makedirs(os.path.dirname(excel_path) or ".", exist_ok=True)
    wb.save(excel_path)


def main():
    parser = argparse.ArgumentParser(
        description="Export watchlist.yaml to an Excel workbook.",
        epilog=(
            "Examples:\n"
            "  python -m src.export_watchlist_to_excel "
            "--yaml watchlist.yaml --excel watchlist.xlsx\n"
            "  python -m src.export_watchlist_to_excel "
            "--yaml watchlist.yaml --excel watchlist.xlsx "
            "--sheet watchlist"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--yaml",
        default="watchlist.yaml",
        help="Path to watchlist YAML file to read (default: watchlist.yaml).",
    )
    parser.add_argument(
        "--excel",
        default="watchlist.xlsx",
        help="Path to Excel file to write (default: watchlist.xlsx).",
    )
    parser.add_argument(
        "--sheet",
        default="watchlist",
        help="Worksheet name to write (default: watchlist).",
    )
    args = parser.parse_args()

    try:
        export_watchlist_to_excel(
            yaml_path=args.yaml,
            excel_path=args.excel,
            sheet_name=args.sheet,
        )
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)

    print(f"[INFO] Exported {args.yaml} -> {args.excel} ({args.sheet})")


if __name__ == "__main__":
    main()
