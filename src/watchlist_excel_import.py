"""Import a watchlist Excel sheet and write watchlist.yaml.

Usage:
    python -m src.watchlist_excel_import --excel watchlist.xlsx \
        --yaml watchlist.yaml

Expected columns (case-insensitive):
- name
- match_keywords (comma-separated)
- exclude_keywords (comma-separated)
- include_unknown_half_price (TRUE/FALSE/Yes/No/1/0)
- only_half_price (TRUE/FALSE/Yes/No/1/0)

Requires: openpyxl, pyyaml
"""

from __future__ import annotations

import argparse
import csv
import os
from io import StringIO
from typing import Dict, List, Optional

import yaml
from openpyxl import load_workbook


def _bool_from_cell(value: object) -> bool:
    """Parse a boolean-like cell value."""
    # Excel cells can come back as native booleans, numbers, or strings
    # depending on how the sheet was edited, so this helper keeps the import
    # path tolerant of all the common representations users tend to enter.
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def _split_keywords(cell_value: object) -> List[str]:
    """Split a CSV-style keywords cell into a list, trimming blanks."""
    if cell_value is None:
        return []
    if isinstance(cell_value, list):
        return [str(x).strip() for x in cell_value if str(x).strip()]
    text = str(cell_value).strip()
    if not text:
        return []

    # The exporter writes the cell with csv.writer so values containing commas
    # round-trip correctly when users open and save the workbook in Excel.
    reader = csv.reader(StringIO(text), skipinitialspace=True)
    parts = next(reader, [])
    return [part.strip() for part in parts if part and part.strip()]


def _load_existing_yaml(yaml_path: str) -> Dict[str, object]:
    """Load the existing YAML mapping so non-item keys survive import."""
    if not os.path.exists(yaml_path):
        return {}

    with open(yaml_path, "r", encoding="utf-8") as f:
        existing = yaml.safe_load(f) or {}

    if not isinstance(existing, dict):
        raise ValueError(f"{yaml_path} must contain a top-level mapping")

    return existing


def import_watchlist_from_excel(
    excel_path: str = "watchlist.xlsx",
    yaml_path: str = "watchlist.yaml",
    sheet_name: Optional[str] = None,
) -> None:
    """Read Excel and write watchlist YAML."""
    wb = load_workbook(excel_path)
    ws = wb[sheet_name] if sheet_name else wb.active

    # Resolve headers once up front so column order in the workbook does not
    # matter, and users can rename headers with different casing safely.
    header_cells = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    header_map: Dict[str, int] = {}
    for idx, name in enumerate(header_cells):
        if not name:
            continue
        key = str(name).strip().lower()
        header_map[key] = idx

    required = {
        "name",
        "match_keywords",
        "exclude_keywords",
        "include_unknown_half_price",
        "only_half_price",
    }
    missing = required - set(header_map.keys())
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    items: List[Dict[str, object]] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        # Skip completely empty rows
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        # A missing name makes the row unusable as a watchlist entry, so treat
        # it as a blank/incomplete row instead of generating malformed YAML.
        name = row[header_map["name"]]
        if not name:
            continue

        keywords_cell = row[header_map["match_keywords"]]
        exclude_keywords_cell = row[header_map["exclude_keywords"]]
        include_unknown_half_price_cell = row[
            header_map["include_unknown_half_price"]
        ]
        only_half_cell = row[header_map["only_half_price"]]

        items.append(
            {
                "name": str(name).strip(),
                "match_keywords": _split_keywords(keywords_cell),
                "exclude_keywords": _split_keywords(exclude_keywords_cell),
                "include_unknown_half_price": _bool_from_cell(
                    include_unknown_half_price_cell
                ),
                "only_half_price": _bool_from_cell(only_half_cell),
            }
        )

    # Preserve any future top-level settings like api_limits and only replace
    # the watchlist items edited through Excel.
    data = _load_existing_yaml(yaml_path)
    data["items"] = items
    os.makedirs(os.path.dirname(yaml_path) or ".", exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=False)


def main():
    parser = argparse.ArgumentParser(
        description="Import an Excel watchlist and write watchlist.yaml.",
    )
    parser.add_argument(
        "--excel",
        default="watchlist.xlsx",
        help="Path to Excel file (input).",
    )
    parser.add_argument(
        "--yaml",
        default="watchlist.yaml",
        help="Path to YAML to write (output).",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Worksheet name (defaults to first sheet).",
    )
    args = parser.parse_args()

    import_watchlist_from_excel(
        excel_path=args.excel,
        yaml_path=args.yaml,
        sheet_name=args.sheet,
    )
    print(
        "[INFO] Imported "
        f"{args.excel} -> {args.yaml} "
        f"({args.sheet or 'active sheet'})"
    )


if __name__ == "__main__":
    main()
