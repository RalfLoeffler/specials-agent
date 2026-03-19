from __future__ import annotations

import os
import ssl
import smtplib
import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from email.message import EmailMessage

import requests
import yaml

"""
Specials checker for Coles & Woolworths via RapidAPI.

What this script does
- Loads a watchlist of products (watchlist.yaml)
- Searches both Coles and Woolworths RapidAPI endpoints for each keyword
- Normalises results and builds a markdown/plain-text report
- Sends the report via Gmail (optional) and records API usage limits

Quick usage
- Inspect API shapes:  python specials_checker.py --test-coles "tim tam"
- Run without email:   python specials_checker.py --no-email
- Run with email:      python specials_checker.py
- Testing mode:        python specials_checker.py --testing
    (prints results, shows API call counts/warnings, no email)

Required setup
- RapidAPI key: set env RAPIDAPI_KEY or config/secrets.yaml: rapidapi_key
- Gmail app password: email_config.yaml (see README)
- Optional limits: config/limits.yaml or api_limits in watchlist.yaml

Notes
- API response shapes can change; use the test flags above to inspect and
    adjust the normalise_* helpers if fields move or rename.
"""


# =========================
# CONFIG
# =========================

def load_rapidapi_key() -> str:
    """Return RapidAPI key from env or config/secrets.yaml."""
    env_key = os.environ.get("RAPIDAPI_KEY", "")
    if env_key:
        return env_key

    secrets_path = os.path.join("config", "secrets.yaml")
    if os.path.exists(secrets_path):
        with open(secrets_path, "r") as f:
            secrets = yaml.safe_load(f) or {}
        file_key = secrets.get("rapidapi_key", "")
        if file_key:
            return str(file_key)

    raise RuntimeError(
        "No RapidAPI key found. Set RAPIDAPI_KEY or add rapidapi_key to "
        "config/secrets.yaml."
    )


RAPIDAPI_KEY = load_rapidapi_key()

COLES_HOST = "coles-product-price-api.p.rapidapi.com"
WOOLIES_HOST = "woolworths-products-api.p.rapidapi.com"

COLES_SEARCH_URL = f"https://{COLES_HOST}/products/search"
WOOLIES_SEARCH_URL = f"https://{WOOLIES_HOST}/products/search"

BASE_HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
}

# Persistent monthly API usage counter stored on disk so Pi restarts do not
# lose usage history; rotated automatically each month.
API_USAGE_PATH = os.path.join("config", "api_usage.json")
API_CALL_COUNT: Dict[str, int] = {
    "Coles": 0,
    "Woolworths": 0,
}

LIMIT_WARNINGS: List[str] = []


class APILimitExceeded(Exception):
    """Raised when a store's hard API limit is reached."""


def _current_month_key() -> str:
    """Month bucket key (UTC) used to reset counters on rollover."""
    return datetime.utcnow().strftime("%Y-%m")


def _coerce_limit_value(value: object) -> Optional[int]:
    """Best-effort int conversion; returns None on invalid input."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _merge_limit(
    base: Dict[str, Optional[int]], override: object
) -> Dict[str, Optional[int]]:
    """Merge warn/hard limit overrides into a base mapping."""
    if not isinstance(override, dict):
        return dict(base)

    merged = dict(base)
    warn_val = _coerce_limit_value(override.get("warn"))
    hard_val = _coerce_limit_value(override.get("hard"))
    if warn_val is not None:
        merged["warn"] = warn_val
    if hard_val is not None:
        merged["hard"] = hard_val
    return merged


def load_limit_config() -> Dict[str, Dict[str, Optional[int]]]:
    """Load per-store warn/hard limits from limits.yaml or watchlist.yaml."""
    limits: Dict[str, Dict[str, Optional[int]]] = {
        "Coles": {"warn": None, "hard": None},
        "Woolworths": {"warn": None, "hard": None},
    }

    candidate_paths = [
        os.path.join("config", "limits.yaml"),
        "watchlist.yaml",
    ]

    for path in candidate_paths:
        if not os.path.exists(path):
            continue

        with open(path, "r") as f:
            raw = yaml.safe_load(f) or {}

        api_limits = raw.get("api_limits") if isinstance(raw, dict) else None
        if not isinstance(api_limits, dict):
            continue

        default_entry = api_limits.get("default", {})
        for key, store_name in (
            ("coles", "Coles"),
            ("woolworths", "Woolworths"),
        ):
            store_entry = api_limits.get(key, {})
            base = _merge_limit(limits.get(store_name, {}), default_entry)
            limits[store_name] = _merge_limit(base, store_entry)
        break

    return limits


LIMIT_CONFIG = load_limit_config()


def _ensure_usage_dir():
    """Create the config directory for the usage file if missing."""
    usage_dir = os.path.dirname(API_USAGE_PATH)
    if usage_dir:
        os.makedirs(usage_dir, exist_ok=True)


def load_api_usage_state() -> Dict[str, object]:
    """Load persisted monthly API counts, resetting on month change."""
    month_key = _current_month_key()
    default_state = {
        "month": month_key,
        "counts": {
            "Coles": 0,
            "Woolworths": 0,
        },
    }

    if not os.path.exists(API_USAGE_PATH):
        return default_state

    try:
        with open(API_USAGE_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        return default_state

    stored_month = data.get("month", month_key)
    counts = data.get("counts", {}) if isinstance(data, dict) else {}

    if stored_month != month_key:
        return default_state

    return {
        "month": stored_month,
        "counts": {
            "Coles": int(counts.get("Coles", 0)),
            "Woolworths": int(counts.get("Woolworths", 0)),
        },
    }


API_USAGE_STATE = load_api_usage_state()
API_CALL_COUNT.update(API_USAGE_STATE.get("counts", {}))


def _save_api_usage_state():
    """Persist current counters to disk."""
    _ensure_usage_dir()
    state = {
        "month": API_USAGE_STATE.get("month", _current_month_key()),
        "counts": API_CALL_COUNT,
    }
    with open(API_USAGE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _reset_month_if_needed():
    """Reset counters and state if the month bucket has rolled over."""
    current_month = _current_month_key()
    if API_USAGE_STATE.get("month") != current_month:
        API_USAGE_STATE["month"] = current_month
        API_USAGE_STATE["counts"] = {"Coles": 0, "Woolworths": 0}
        API_CALL_COUNT.clear()
        API_CALL_COUNT.update(API_USAGE_STATE["counts"])
        _save_api_usage_state()


def _record_limit_warning(message: str):
    """Deduplicate and store a limit warning message."""
    if message not in LIMIT_WARNINGS:
        LIMIT_WARNINGS.append(message)


def _limits_for_store(store: str) -> Dict[str, Optional[int]]:
    """Return warn/hard limits for a store, with None if unset."""
    return LIMIT_CONFIG.get(store, {"warn": None, "hard": None})


def _maybe_warn_limit(store: str):
    """Append a warning when the store crosses its warn threshold."""
    limits = _limits_for_store(store)
    warn_limit = limits.get("warn")
    count = API_CALL_COUNT.get(store, 0)
    if warn_limit is not None and count >= warn_limit:
        _record_limit_warning(
            f"{store} API calls are at {count} (warn threshold {warn_limit})."
        )


def _enforce_hard_limit(store: str):
    """Raise when the store has reached its hard cap."""
    limits = _limits_for_store(store)
    hard_limit = limits.get("hard")
    if hard_limit is not None and API_CALL_COUNT.get(store, 0) >= hard_limit:
        raise APILimitExceeded(
            store,
            (
                f"{store} API hard limit ({hard_limit}) reached; "
                "aborting to avoid overage."
            ),
        )


def _record_api_call(store: str):
    """Track one API call, enforcing hard limits and persisting state."""
    # Order matters: reset month, enforce hard stop, then increment + persist.
    _reset_month_if_needed()
    _enforce_hard_limit(store)
    API_CALL_COUNT[store] = API_CALL_COUNT.get(store, 0) + 1
    API_USAGE_STATE["counts"] = API_CALL_COUNT
    _save_api_usage_state()
    _maybe_warn_limit(store)


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
    """Load watch items from YAML into WatchItem objects."""
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
    """Perform a RapidAPI GET with required host/key headers."""
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
    _record_api_call("Coles")
    params = {
        "query": keyword,   # use 'q' or 'productName' if API shape changes
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
    _record_api_call("Woolworths")
    params = {
        "query": keyword,   # use 'q' or 'searchTerm' if API shape changes
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
    """Search both stores for each keyword, normalising offers."""
    offers: List[Offer] = []

    for kw in watch_item.match_keywords:
        jobs = [
            ("Coles", search_coles, normalise_coles_product),
            ("Woolworths", search_woolies, normalise_woolies_product),
        ]

        for store, search_fn, normalise_fn in jobs:
            try:
                data = search_fn(kw)
                products = extract_products_from_response(data)
                offers.extend(
                    [normalise_fn(watch_item.name, raw) for raw in products]
                )
            except APILimitExceeded:
                # Bubble up immediately so the caller can stop the run.
                raise
            except Exception as e:
                print(f"[WARN] {store} search failed for '{kw}': {e}")

    if watch_item.only_half_price:
        offers = [o for o in offers if o.is_half_price]

    return offers


def build_report(
    all_offers: Dict[str, List[Offer]],
    limit_warnings: Optional[List[str]] = None,
) -> str:
    """Render a text report plus optional API usage warnings."""
    lines: List[str] = []

    if limit_warnings:
        # Surface any API usage warnings at the top of the email/console.
        lines.append("## API usage warnings")
        for msg in limit_warnings:
            lines.append(f"- {msg}")
        lines.append("")
    for watch_name, offers in all_offers.items():
        lines.append(f"## {watch_name}")
        if not offers:
            lines.append("No matching products or specials found.\n")
            continue

        offers_sorted = sorted(offers, key=lambda o: (o.store, o.price))

        # group by store to find cheapest in each
        cheapest_by_store: Dict[str, Offer] = {}
        for o in offers_sorted:
            if (
                o.store not in cheapest_by_store
                or o.price < cheapest_by_store[o.store].price
            ):
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
            lines.append(
                f"**Cheapest overall:** {cheapest.store} "
                f"at ${cheapest.price:.2f}"
            )

        lines.append("")  # blank line

    return "\n".join(lines)


# =========================
# EMAIL SENDER (GMAIL)
# =========================

def send_email_report(
    report: str, subject: str = "Weekly grocery specials report"
):
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

def main(send_email: bool = True, testing_mode: bool = False):
    """Run the full flow: load watchlist, fetch offers, report, email."""
    watchlist = load_watchlist("watchlist.yaml")
    all_offers: Dict[str, List[Offer]] = {}

    limit_error: Optional[str] = None
    try:
        for wi in watchlist:
            all_offers[wi.name] = find_offers_for_watch_item(wi)
    except APILimitExceeded as e:
        limit_error = str(e)
        _record_limit_warning(limit_error)
        print(f"[ERROR] {limit_error}")

    report = build_report(all_offers, limit_warnings=LIMIT_WARNINGS)
    print(report)

    if testing_mode:
        print("[INFO] Testing mode: email send skipped.")
        print(
            "[INFO] API calls — Coles: "
            f"{API_CALL_COUNT.get('Coles', 0)}, "
            "Woolworths: "
            f"{API_CALL_COUNT.get('Woolworths', 0)}"
        )
        if LIMIT_WARNINGS:
            print("[INFO] API usage warnings:")
            for msg in LIMIT_WARNINGS:
                print(f"  - {msg}")

    if send_email and not testing_mode and report.strip():
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
        help=(
            "Test Woolworths API with a search keyword "
            "and print sample products."
        ),
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Run the full checker but do not send an email.",
    )
    parser.add_argument(
        "--testing",
        action="store_true",
        help="Run the checker in testing mode (prints results, no email)",
    )

    args = parser.parse_args()

    if args.test_coles:
        run_test_coles(args.test_coles)
    elif args.test_woolies:
        run_test_woolies(args.test_woolies)
    else:
        suppress_email = args.no_email or args.testing
        main(send_email=not suppress_email, testing_mode=args.testing)
