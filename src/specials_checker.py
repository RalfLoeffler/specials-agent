from __future__ import annotations

import os
import ssl
import smtplib
import argparse
import json
from dataclasses import dataclass
from typing import List, Optional, Dict
from email.message import EmailMessage

import requests
import yaml

"""
Specials checker for Coles & Woolworths via RapidAPI.

You MUST:
- Create a RapidAPI account.
- Subscribe to:
    - Coles Product Price API: https://rapidapi.com/data-holdings-group-data-holdings-group-default/api/coles-product-price-api
    - Woolworths Products API: https://rapidapi.com/data-holdings-group-data-holdings-group-default/api/woolworths-products-api
- Obtain your X-RapidAPI-Key.
- Set RAPIDAPI_KEY in the environment.

IMPORTANT: Field names and response shapes for these APIs can change.
Use the --test-coles / --test-woolies commands to inspect real responses
and adjust the normalisation functions if needed.
"""


# =========================
# CONFIG
# =========================

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")

if not RAPIDAPI_KEY:
    raise RuntimeError(
        "RAPIDAPI_KEY environment variable is not set. "
        "Export it before running:\\n"
        "  export RAPIDAPI_KEY='your_key_here'  (macOS/Linux)\\n"
        "  $env:RAPIDAPI_KEY='your_key_here'    (Windows PowerShell)"
    )

COLES_HOST = "coles-product-price-api.p.rapidapi.com"
WOOLIES_HOST = "woolworths-products-api.p.rapidapi.com"

COLES_SEARCH_URL = f"https://{COLES_HOST}/products/search"
WOOLIES_SEARCH_URL = f"https://{WOOLIES_HOST}/products/search"

BASE_HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
}


# =========================
# DATA MODELS
# =========================

@dataclass
class WatchItem:
    name: str
    match_keywords: List[str]
    only_half_price: bool = False


@dataclass
class Offer:
    watch_name: str
    store: str            # "Coles" or "Woolworths"
    product_title: str
    price: float
    size: Optional[str]
    url: str
    was_price: Optional[float] = None
    is_half_price: bool = False


# =========================
# WATCHLIST LOADER
# =========================

def load_watchlist(path: str = "watchlist.yaml") -> List[WatchItem]:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    items: List[WatchItem] = []
    for raw in data.get("items", []):
        items.append(
            WatchItem(
                name=raw["name"],
                match_keywords=list(raw["match_keywords"]),
                only_half_price=bool(raw.get("only_half_price", False)),
            )
        )
    return items


# =========================
# LOW-LEVEL API CALLER
# =========================

def rapidapi_get(url: str, host: str, params: dict) -> dict:
    headers = dict(BASE_HEADERS)
    headers["X-RapidAPI-Host"] = host

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


# =========================
# SEARCH WRAPPERS
# =========================

def search_coles(keyword: str, page_size: int = 10) -> dict:
    """
    Search Coles Product Price API by keyword.

    Returns the full JSON dict (not just products) so the test functions
    can inspect shape. Normalisation helpers will extract products.
    """
    params = {
        "query": keyword,   # sometimes 'q' or 'productName' – check docs if needed
        "pageSize": page_size,
        "pageNumber": 1,
    }
    data = rapidapi_get(COLES_SEARCH_URL, COLES_HOST, params)
    return data


def search_woolies(keyword: str, page_size: int = 10) -> dict:
    """
    Search Woolworths Products API by keyword.

    Returns full JSON dict.
    """
    params = {
        "query": keyword,   # sometimes 'q' or 'searchTerm' – check docs if needed
        "pageSize": page_size,
        "pageNumber": 1,
    }
    data = rapidapi_get(WOOLIES_SEARCH_URL, WOOLIES_HOST, params)
    return data


def extract_products_from_response(data: dict) -> List[dict]:
    """
    Tries to find the list of products in a typical RapidAPI response.
    Adjust if the API uses a different structure.
    """
    candidates = [
        data.get("results") if isinstance(data, dict) else None,
        data.get("data") if isinstance(data, dict) else None,
        data.get("products") if isinstance(data, dict) else None,
    ]
    for cand in candidates:
        if isinstance(cand, list):
            return cand
    # Fallback: if the data itself is a list or a single product
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # maybe response is a single product; wrap in list
        return [data]
    return []


# =========================
# NORMALISATION HELPERS
# =========================

def normalise_coles_product(watch_name: str, raw: dict) -> Offer:
    """
    Convert one Coles product JSON object into an Offer.

    After first run, adjust field names below to match the real JSON.
    Use:
        python specials_checker.py --test-coles "tim tam"
    to see examples.
    """
    title = (
        raw.get("name")
        or raw.get("productName")
        or raw.get("ProductName")
        or "Unknown Coles product"
    )

    price_val = (
        raw.get("currentPrice")
        or raw.get("price")
        or raw.get("CurrentPrice")
    )
    if price_val is None:
        raise ValueError(f"No price field found in Coles product: {raw}")
    price = float(price_val)

    was_val = (
        raw.get("wasPrice")
        or raw.get("WasPrice")
        or raw.get("originalPrice")
        or raw.get("PreviousPrice")
    )
    was_price = float(was_val) if was_val not in (None, "") else None

    size = (
        raw.get("size")
        or raw.get("Size")
        or raw.get("packageSize")
        or raw.get("PackageSize")
    )

    url = (
        raw.get("url")
        or raw.get("Url")
        or raw.get("productUrl")
        or raw.get("ProductUrl")
        or ""
    )

    is_half_price = False
    if was_price:
        is_half_price = price <= was_price / 2 + 0.01

    return Offer(
        watch_name=watch_name,
        store="Coles",
        product_title=str(title),
        price=price,
        size=str(size) if size is not None else "",
        url=str(url),
        was_price=was_price,
        is_half_price=is_half_price,
    )


def normalise_woolies_product(watch_name: str, raw: dict) -> Offer:
    """
    Convert one Woolworths product JSON object into an Offer.

    After first run, adjust field names below to match the real JSON.
    Use:
        python specials_checker.py --test-woolies "tim tam"
    to see examples.
    """
    title = (
        raw.get("name")
        or raw.get("productName")
        or raw.get("ProductName")
        or raw.get("description")
        or raw.get("Description")
        or "Unknown Woolworths product"
    )

    price_val = (
        raw.get("currentPrice")
        or raw.get("price")
        or raw.get("CurrentPrice")
        or raw.get("Price")
    )
    if price_val is None:
        raise ValueError(f"No price field found in Woolies product: {raw}")
    price = float(price_val)

    was_val = (
        raw.get("wasPrice")
        or raw.get("WasPrice")
        or raw.get("originalPrice")
        or raw.get("PreviousPrice")
    )
    was_price = float(was_val) if was_val not in (None, "") else None

    size = (
        raw.get("size")
        or raw.get("Size")
        or raw.get("packageSize")
        or raw.get("PackageSize")
    )

    url = (
        raw.get("url")
        or raw.get("Url")
        or raw.get("productUrl")
        or raw.get("ProductUrl")
        or ""
    )

    is_half_price = False
    if was_price:
        is_half_price = price <= was_price / 2 + 0.01

    return Offer(
        watch_name=watch_name,
        store="Woolworths",
        product_title=str(title),
        price=price,
        size=str(size) if size is not None else "",
        url=str(url),
        was_price=was_price,
        is_half_price=is_half_price,
    )


# =========================
# CORE LOGIC
# =========================

def find_offers_for_watch_item(watch_item: WatchItem) -> List[Offer]:
    offers: List[Offer] = []

    for kw in watch_item.match_keywords:
        # Coles
        try:
            coles_data = search_coles(kw)
            for raw in extract_products_from_response(coles_data):
                offers.append(normalise_coles_product(watch_item.name, raw))
        except Exception as e:
            print(f"[WARN] Coles search failed for '{kw}': {e}")

        # Woolworths
        try:
            woolies_data = search_woolies(kw)
            for raw in extract_products_from_response(woolies_data):
                offers.append(normalise_woolies_product(watch_item.name, raw))
        except Exception as e:
            print(f"[WARN] Woolies search failed for '{kw}': {e}")

    if watch_item.only_half_price:
        offers = [o for o in offers if o.is_half_price]

    return offers


def build_report(all_offers: Dict[str, List[Offer]]) -> str:
    lines: List[str] = []
    for watch_name, offers in all_offers.items():
        lines.append(f"## {watch_name}")
        if not offers:
            lines.append("No matching products or specials found.\n")
            continue

        offers_sorted = sorted(offers, key=lambda o: (o.store, o.price))

        # group by store to find cheapest in each
        cheapest_by_store: Dict[str, Offer] = {}
        for o in offers_sorted:
            if o.store not in cheapest_by_store or o.price < cheapest_by_store[o.store].price:
                cheapest_by_store[o.store] = o

        for o in offers_sorted:
            was_str = f"(was ${o.was_price:.2f})" if o.was_price else ""
            half_str = " [HALF PRICE?]" if o.is_half_price else ""
            size_str = f" – {o.size}" if o.size else ""
            url_str = f" – {o.url}" if o.url else ""
            lines.append(
                f"- {o.store}: {o.product_title} – ${o.price:.2f} "
                f"{was_str}{half_str}{size_str}{url_str}"
            )

        if len(cheapest_by_store) >= 2:
            cheapest = min(cheapest_by_store.values(), key=lambda o: o.price)
            lines.append(f"**Cheapest overall:** {cheapest.store} at ${cheapest.price:.2f}")

        lines.append("")  # blank line

    return "\n".join(lines)


# =========================
# EMAIL SENDER (GMAIL)
# =========================

def send_email_report(report: str, subject: str = "Weekly grocery specials report"):
    """
    Sends the report via Gmail using an app password.

    Reads credentials from email_config.yaml in the same directory.
    """
    if not os.path.exists("email_config.yaml"):
        print("[WARN] email_config.yaml not found, skipping email send.")
        return

    with open("email_config.yaml", "r") as f:
        cfg = yaml.safe_load(f)

    gmail_user = cfg["gmail_user"]
    gmail_app_password = cfg["gmail_app_password"]
    to_email = cfg.get("to_email", gmail_user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to_email
    msg.set_content(report)

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls(context=context)
        server.login(gmail_user, gmail_app_password)
        server.send_message(msg)
    print(f"[INFO] Report emailed to {to_email}")


# =========================
# TEST / DEBUG HELPERS
# =========================

def pretty_print_sample(data: dict, max_items: int = 3):
    """
    Print top-level keys and a few product entries for debugging.
    """
    if isinstance(data, dict):
        print("Top-level keys:", list(data.keys()))
    else:
        print("Top-level type:", type(data))

    products = extract_products_from_response(data)
    print(f"Detected {len(products)} product(s)")
    for i, prod in enumerate(products[:max_items]):
        print(f"\\n--- Product #{i+1} ---")
        print(json.dumps(prod, indent=2, sort_keys=True))


def run_test_coles(keyword: str):
    print(f"[TEST] Coles search for: {keyword!r}")
    data = search_coles(keyword)
    pretty_print_sample(data)


def run_test_woolies(keyword: str):
    print(f"[TEST] Woolworths search for: {keyword!r}")
    data = search_woolies(keyword)
    pretty_print_sample(data)


# =========================
# ENTRY POINT
# =========================

def main(send_email: bool = True):
    watchlist = load_watchlist("watchlist.yaml")
    all_offers: Dict[str, List[Offer]] = {}

    for wi in watchlist:
        all_offers[wi.name] = find_offers_for_watch_item(wi)

    report = build_report(all_offers)
    print(report)

    if send_email and report.strip():
        send_email_report(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Coles/Woolworths specials checker via RapidAPI."
    )
    parser.add_argument(
        "--test-coles",
        metavar="KEYWORD",
        help="Test Coles API with a search keyword and print sample products.",
    )
    parser.add_argument(
        "--test-woolies",
        metavar="KEYWORD",
        help="Test Woolworths API with a search keyword and print sample products.",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Run the full checker but do not send an email.",
    )

    args = parser.parse_args()

    if args.test_coles:
        run_test_coles(args.test_coles)
    elif args.test_woolies:
        run_test_woolies(args.test_woolies)
    else:
        main(send_email=not args.no_email)
