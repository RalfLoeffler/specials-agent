"""Import a watchlist Excel sheet and write watchlist.yaml.

Usage:
    python -m src.watchlist_excel_import --excel watchlist.xlsx \
        --yaml watchlist.yaml

Expected columns (case-insensitive):
- name
- match_keywords (comma-separated)
- only_half_price (TRUE/FALSE/Yes/No/1/0)

Requires: openpyxl, pyyaml
"""
from __future__ import annotations

import argparse
import os
from typing import Dict, List, Optional

import yaml
from openpyxl import load_workbook


def _bool_from_cell(value: object) -> bool:
    """Parse a boolean-like cell value."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def _split_keywords(cell_value: object) -> List[str]:
    """Split comma-separated keywords into a list, trimming blanks."""
    if cell_value is None:
        return []
    if isinstance(cell_value, list):
        return [str(x).strip() for x in cell_value if str(x).strip()]
    text = str(cell_value)
    parts = [p.strip() for p in text.split(",")]
    return [p for p in parts if p]


def import_watchlist_from_excel(
    excel_path: str = "watchlist.xlsx",
    yaml_path: str = "watchlist.yaml",
    sheet_name: Optional[str] = None,
) -> None:
    """Read Excel and write watchlist YAML."""
    wb = load_workbook(excel_path)
    ws = wb[sheet_name] if sheet_name else wb.active

    # Map header names to column index
    header_cells = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    header_map: Dict[str, int] = {}
    for idx, name in enumerate(header_cells):
        if not name:
            continue
        key = str(name).strip().lower()
        header_map[key] = idx

    required = {"name", "match_keywords", "only_half_price"}
    missing = required - set(header_map.keys())
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    items: List[Dict[str, object]] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        # Skip completely empty rows
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        name = row[header_map["name"]]
        if not name:
            continue

        keywords_cell = row[header_map["match_keywords"]]
        only_half_cell = row[header_map["only_half_price"]]

        items.append(
            {
                "name": str(name).strip(),
                "match_keywords": _split_keywords(keywords_cell),
                "only_half_price": _bool_from_cell(only_half_cell),
            }
        )

    data = {"items": items}
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
