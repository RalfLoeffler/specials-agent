from __future__ import annotations

import argparse
import json
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

"""
Specials checker for Coles & Woolworths via RapidAPI.

What this script does
- Loads a watchlist of products (watchlist.yaml)
- Searches both Coles and Woolworths product search endpoints
- Normalises results and builds a markdown/plain-text report
- Sends the report via Gmail (optional) and records API usage limits
"""


# =========================
# CONFIG
# =========================

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 20
MAX_PAGES_PER_KEYWORD = 2


def load_rapidapi_key() -> str:
    """Return RapidAPI key from env or config/secrets.yaml."""
    env_key = os.environ.get("RAPIDAPI_KEY", "")
    if env_key:
        return env_key

    secrets_path = os.path.join("config", "secrets.yaml")
    if os.path.exists(secrets_path):
        with open(secrets_path, "r", encoding="utf-8") as f:
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

COLES_PRODUCT_SEARCH_URL = f"https://{COLES_HOST}/coles/product-search/"
WOOLIES_PRODUCT_SEARCH_URL = f"https://{WOOLIES_HOST}/woolworths/product-search/"

BASE_HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
}
SEARCH_RESPONSE_CACHE: Dict[Tuple[str, str, int, int], dict] = {}

API_USAGE_PATH = os.path.join("config", "api_usage.json")
EMAIL_CONFIG_PATHS = [
    os.path.join("config", "email_config.yaml"),
    "email_config.yaml",
]
API_CALL_COUNT: Dict[str, int] = {
    "Coles": 0,
    "Woolworths": 0,
}
RUN_API_CALL_COUNT: Dict[str, int] = {
    "Coles": 0,
    "Woolworths": 0,
}

LIMIT_WARNINGS: List[str] = []


class APILimitExceeded(Exception):
    """Raised when a store's hard API limit is reached."""


def resolve_email_config_path() -> Optional[str]:
    """Return the preferred existing email config path, if any."""
    for path in EMAIL_CONFIG_PATHS:
        if os.path.exists(path):
            return path
    return None


def load_email_config() -> Tuple[Optional[str], Dict[str, Any]]:
    """Load the email config file, returning its path and parsed mapping."""
    email_config_path = resolve_email_config_path()
    if email_config_path is None:
        return None, {}

    with open(email_config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    if not isinstance(cfg, dict):
        raise ValueError(f"{email_config_path} must contain a top-level mapping")

    return email_config_path, cfg


def _current_month_key() -> str:
    """Month bucket key (UTC) used to reset counters on rollover."""
    return datetime.now(UTC).strftime("%Y-%m")


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

        with open(path, "r", encoding="utf-8") as f:
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
        with open(API_USAGE_PATH, "r", encoding="utf-8") as f:
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
    with open(API_USAGE_PATH, "w", encoding="utf-8") as f:
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
    _reset_month_if_needed()
    _enforce_hard_limit(store)
    API_CALL_COUNT[store] = API_CALL_COUNT.get(store, 0) + 1
    RUN_API_CALL_COUNT[store] = RUN_API_CALL_COUNT.get(store, 0) + 1
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
    exclude_keywords: List[str]
    stores: List[str]
    include_unknown_half_price: bool = True
    only_half_price: bool = False


@dataclass
class Offer:
    watch_name: str
    store: str
    product_title: str
    brand: Optional[str]
    price: float
    size: Optional[str]
    url: str
    barcode: Optional[str] = None
    was_price: Optional[float] = None
    is_half_price: bool = False


# =========================
# WATCHLIST LOADER
# =========================


def load_watchlist(path: str = "watchlist.yaml") -> List[WatchItem]:
    """Load watch items from YAML into WatchItem objects."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw_items = data.get("items", []) if isinstance(data, dict) else []
    items: List[WatchItem] = []
    for raw in raw_items:
        items.append(
            WatchItem(
                name=raw["name"],
                match_keywords=list(raw["match_keywords"]),
                exclude_keywords=list(raw.get("exclude_keywords", [])),
                stores=_normalise_watch_stores(raw.get("stores")),
                include_unknown_half_price=bool(
                    raw.get("include_unknown_half_price", True)
                ),
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


def search_coles(
    keyword: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    page_number: int = 1,
) -> dict:
    """Search Coles products by keyword."""
    cache_key = ("Coles", keyword.strip().lower(), page_size, page_number)
    cached = SEARCH_RESPONSE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    _record_api_call("Coles")
    params = {
        "query": keyword,
        "page_size": max(1, min(page_size, MAX_PAGE_SIZE)),
        "page": max(1, page_number),
    }
    response = rapidapi_get(COLES_PRODUCT_SEARCH_URL, COLES_HOST, params)
    SEARCH_RESPONSE_CACHE[cache_key] = response
    return response


def search_woolies(
    keyword: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    page_number: int = 1,
) -> dict:
    """Search Woolworths products by keyword."""
    cache_key = ("Woolworths", keyword.strip().lower(), page_size, page_number)
    cached = SEARCH_RESPONSE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    _record_api_call("Woolworths")
    params = {
        "query": keyword,
        "page_size": max(1, min(page_size, MAX_PAGE_SIZE)),
        "page": max(1, page_number),
    }
    response = rapidapi_get(WOOLIES_PRODUCT_SEARCH_URL, WOOLIES_HOST, params)
    SEARCH_RESPONSE_CACHE[cache_key] = response
    return response


def _as_mapping(value: object) -> Dict[str, Any]:
    """Return a dict-like payload or an empty mapping."""
    return value if isinstance(value, dict) else {}


def _pick_first(raw: Dict[str, Any], *keys: str) -> Any:
    """Return the first non-empty key value from a raw API product payload."""
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _coerce_float(value: object) -> Optional[float]:
    """Convert common numeric payload shapes into a float."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        nested = _pick_first(
            value,
            "current",
            "value",
            "amount",
            "price",
            "Price",
            "CurrentPrice",
        )
        return _coerce_float(nested)

    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_str(value: object) -> Optional[str]:
    """Normalise an optional scalar value to a trimmed string."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def extract_products_from_response(data: dict) -> List[dict]:
    """Find the product list in a RapidAPI-style response."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    nested = _as_mapping(data.get("data"))
    candidates = [
        data.get("results"),
        nested.get("results"),
        data.get("products"),
        nested.get("products"),
        data.get("items"),
        nested.get("items"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]

    if (
        "query" in data
        or "totalPages" in data
        or "total_pages" in data
        or "totalResults" in data
        or "total_results" in data
    ):
        return []
    return [data]


def extract_pagination_from_response(data: dict) -> Tuple[int, int, Optional[int]]:
    """Read current page and total pages/results from a response."""
    if not isinstance(data, dict):
        return 1, 1, None

    nested = _as_mapping(data.get("data"))
    current_page = _coerce_float(
        _pick_first(data, "currentPage", "current_page", "pageNumber", "page")
    ) or _coerce_float(
        _pick_first(nested, "currentPage", "current_page", "pageNumber", "page")
    )
    total_pages = _coerce_float(
        _pick_first(data, "totalPages", "total_pages", "pageCount")
    ) or _coerce_float(_pick_first(nested, "totalPages", "total_pages", "pageCount"))
    total_results = _coerce_float(
        _pick_first(data, "totalResults", "total_results", "count", "total")
    ) or _coerce_float(
        _pick_first(nested, "totalResults", "total_results", "count", "total")
    )

    return (
        int(current_page or 1),
        max(1, int(total_pages or 1)),
        int(total_results) if total_results is not None else None,
    )


# =========================
# NORMALISATION HELPERS
# =========================


def normalise_coles_product(watch_name: str, raw: dict) -> Offer:
    """Convert one Coles search result into an Offer."""
    title = (
        _coerce_str(
            _pick_first(
                raw,
                "product_name",
                "name",
                "productName",
                "ProductName",
                "title",
            )
        )
        or "Unknown Coles product"
    )
    brand = _coerce_str(
        _pick_first(raw, "product_brand", "brand", "productBrand", "Brand")
    )
    price = _coerce_float(
        _pick_first(raw, "current_price", "currentPrice", "price", "CurrentPrice")
    )
    if price is None:
        raise ValueError(f"No price field found in Coles product: {raw}")

    was_price = _coerce_float(
        _pick_first(
            raw,
            "was_price",
            "old_price",
            "wasPrice",
            "WasPrice",
            "originalPrice",
            "PreviousPrice",
        )
    )
    size = _coerce_str(_pick_first(raw, "size", "Size", "packageSize", "PackageSize"))
    url = _coerce_str(_pick_first(raw, "url", "Url", "productUrl", "ProductUrl")) or ""
    is_half_price = bool(was_price and price <= was_price / 2 + 0.01)

    return Offer(
        watch_name=watch_name,
        store="Coles",
        product_title=title,
        brand=brand,
        price=price,
        size=size or "",
        url=url,
        was_price=was_price,
        is_half_price=is_half_price,
    )


def normalise_woolies_product(watch_name: str, raw: dict) -> Offer:
    """Convert one Woolworths search result into an Offer."""
    title = (
        _coerce_str(
            _pick_first(
                raw,
                "product_name",
                "name",
                "productName",
                "ProductName",
                "description",
                "Description",
                "title",
            )
        )
        or "Unknown Woolworths product"
    )
    brand = _coerce_str(
        _pick_first(raw, "product_brand", "brand", "productBrand", "Brand")
    )
    barcode = _coerce_str(_pick_first(raw, "barcode", "Barcode", "gtin", "GTIN"))
    price = _coerce_float(
        _pick_first(
            raw,
            "current_price",
            "currentPrice",
            "price",
            "CurrentPrice",
            "Price",
        )
    )
    if price is None:
        raise ValueError(f"No price field found in Woolworths product: {raw}")

    was_price = _coerce_float(
        _pick_first(
            raw,
            "was_price",
            "old_price",
            "wasPrice",
            "WasPrice",
            "originalPrice",
            "PreviousPrice",
        )
    )
    size = _coerce_str(_pick_first(raw, "size", "Size", "packageSize", "PackageSize"))
    url = _coerce_str(_pick_first(raw, "url", "Url", "productUrl", "ProductUrl")) or ""
    is_half_price = bool(was_price and price <= was_price / 2 + 0.01)

    return Offer(
        watch_name=watch_name,
        store="Woolworths",
        product_title=title,
        brand=brand,
        price=price,
        size=size or "",
        url=url,
        barcode=barcode,
        was_price=was_price,
        is_half_price=is_half_price,
    )


# =========================
# CORE LOGIC
# =========================


def _dedupe_offers(offers: List[Offer]) -> List[Offer]:
    """Remove duplicates caused by overlapping keywords and paged results."""
    deduped: Dict[Tuple[object, ...], Offer] = {}
    for offer in offers:
        key = (
            offer.store,
            (offer.barcode or "").lower(),
            offer.product_title.strip().lower(),
            (offer.size or "").strip().lower(),
            round(offer.price, 2),
            offer.url.strip().lower(),
        )
        deduped.setdefault(key, offer)
    return list(deduped.values())


def _normalise_match_text(value: Optional[str]) -> str:
    """Normalise text for smarter include/exclude keyword matching."""
    text = (value or "").strip().lower()
    # Remove apostrophes so "smith's" and "smiths" collapse to the same base
    # form before token matching, then replace other punctuation with spaces.
    text = text.replace("'", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _tokenise_match_text(value: Optional[str]) -> List[str]:
    """Split normalised text into comparable tokens."""
    text = _normalise_match_text(value)
    return text.split() if text else []


def _token_variants(token: str) -> set[str]:
    """Return simple singular/plural variants for a token."""
    variants = {token}
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        variants.add(token[:-1])
    if len(token) > 4 and token.endswith("ies"):
        variants.add(f"{token[:-3]}y")
    return variants


def _searchable_offer_text(offer: Offer) -> str:
    """Build one searchable text blob from the main comparable fields."""
    return " ".join(
        part
        for part in [
            _normalise_match_text(offer.product_title),
            _normalise_match_text(offer.brand),
            _normalise_match_text(offer.size),
        ]
        if part
    )


def _keyword_matches_offer(keyword: str, offer: Offer) -> bool:
    """Return True when a keyword meaningfully matches an offer."""
    keyword_text = _normalise_match_text(keyword)
    if not keyword_text:
        return False

    searchable_text = _searchable_offer_text(offer)
    if not searchable_text:
        return False

    # Prefer phrase matching first because it is the most precise signal.
    if f" {keyword_text} " in f" {searchable_text} ":
        return True

    keyword_tokens = _tokenise_match_text(keyword)
    if not keyword_tokens:
        return False

    searchable_tokens = _tokenise_match_text(searchable_text)
    searchable_token_variants = {
        variant for token in searchable_tokens for variant in _token_variants(token)
    }

    # Fall back to token coverage so "smiths" can still match a keyword like
    # "smith chips", while avoiding raw substring false positives.
    return all(
        any(variant in searchable_token_variants for variant in _token_variants(token))
        for token in keyword_tokens
    )


def _normalise_keyword_for_search(keyword: str) -> str:
    """Return a stable keyword form for API search deduplication."""
    return _normalise_match_text(keyword)


def _normalise_store_name(value: object) -> Optional[str]:
    """Map common store aliases to the internal display names."""
    if value is None:
        return None

    text = str(value).strip().lower()
    alias_map = {
        "coles": "Coles",
        "woolworths": "Woolworths",
        "woolies": "Woolworths",
    }
    return alias_map.get(text)


def _normalise_watch_stores(raw_stores: object) -> List[str]:
    """Return the allowed stores for a watch item, defaulting to both."""
    if raw_stores in (None, "", []):
        return ["Coles", "Woolworths"]

    if isinstance(raw_stores, str):
        candidate_values = [part.strip() for part in raw_stores.split(",")]
    elif isinstance(raw_stores, list):
        candidate_values = [str(value).strip() for value in raw_stores]
    else:
        raise ValueError(
            "watchlist.yaml stores must be a string or list of store names"
        )

    normalised: List[str] = []
    for value in candidate_values:
        if not value:
            continue
        if value.strip().lower() == "both":
            return ["Coles", "Woolworths"]
        store_name = _normalise_store_name(value)
        if store_name and store_name not in normalised:
            normalised.append(store_name)

    return normalised or ["Coles", "Woolworths"]


def _search_signature_token(token: str) -> str:
    """Collapse simple spelling variants to one search-signature token."""
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    return token


def _keyword_search_signature(keyword: str) -> Tuple[str, ...]:
    """Build a loose signature so near-equivalent search phrases collapse."""
    return tuple(
        _search_signature_token(token) for token in _tokenise_match_text(keyword)
    )


def _derive_search_keywords(match_keywords: List[str]) -> List[str]:
    """Choose a compact set of API search terms from the match keywords."""
    chosen: Dict[Tuple[str, ...], str] = {}
    for keyword in match_keywords:
        signature = _keyword_search_signature(keyword)
        if not signature:
            continue

        current = chosen.get(signature)
        # Prefer the shortest phrase for the API query because broader search
        # terms usually return the same family of products with fewer misses.
        if current is None or len(keyword.strip()) < len(current.strip()):
            chosen[signature] = keyword

    return list(chosen.values())


def _collect_keyword_offers(
    watch_item: WatchItem,
    keyword: str,
    store: str,
    search_fn,
    normalise_fn,
) -> List[Offer]:
    """Fetch the first few pages for one store/keyword pair."""
    offers: List[Offer] = []

    first_page = search_fn(keyword, page_size=DEFAULT_PAGE_SIZE, page_number=1)
    raw_products = extract_products_from_response(first_page)
    offers.extend([normalise_fn(watch_item.name, raw) for raw in raw_products])

    current_page, total_pages, _ = extract_pagination_from_response(first_page)
    last_page = min(total_pages, MAX_PAGES_PER_KEYWORD)
    for page_number in range(max(2, current_page + 1), last_page + 1):
        paged_data = search_fn(
            keyword,
            page_size=DEFAULT_PAGE_SIZE,
            page_number=page_number,
        )
        paged_products = extract_products_from_response(paged_data)
        offers.extend([normalise_fn(watch_item.name, raw) for raw in paged_products])

    return offers


def collect_offers_by_keyword(watchlist: List[WatchItem]) -> Dict[str, List[Offer]]:
    """Search each unique keyword once per store and reuse the results."""
    offers_by_keyword: Dict[str, List[Offer]] = {}
    seen_keywords: Dict[str, str] = {}
    keyword_stores: Dict[str, set[str]] = {}

    for watch_item in watchlist:
        for keyword in _derive_search_keywords(watch_item.match_keywords):
            normalised_keyword = _normalise_keyword_for_search(keyword)
            if not normalised_keyword:
                continue
            seen_keywords.setdefault(normalised_keyword, keyword)
            keyword_stores.setdefault(normalised_keyword, set()).update(
                watch_item.stores
            )

    jobs = {
        "Coles": (search_coles, normalise_coles_product),
        "Woolworths": (search_woolies, normalise_woolies_product),
    }

    for normalised_keyword, keyword in seen_keywords.items():
        keyword_offers: List[Offer] = []
        for store in ("Coles", "Woolworths"):
            if store not in keyword_stores.get(normalised_keyword, set()):
                continue
            search_fn, normalise_fn = jobs[store]
            try:
                keyword_offers.extend(
                    _collect_keyword_offers(
                        WatchItem(
                            name=keyword,
                            match_keywords=[keyword],
                            exclude_keywords=[],
                            stores=[store],
                            include_unknown_half_price=True,
                            only_half_price=False,
                        ),
                        keyword,
                        store,
                        search_fn,
                        normalise_fn,
                    )
                )
            except APILimitExceeded:
                raise
            except Exception as exc:
                print(f"[WARN] {store} search failed for '{keyword}': {exc}")

        offers_by_keyword[normalised_keyword] = _dedupe_offers(keyword_offers)

    return offers_by_keyword


def find_offers_for_watch_item(
    watch_item: WatchItem, offers_by_keyword: Dict[str, List[Offer]]
) -> List[Offer]:
    """Reuse searched keyword results and filter them for one watch item."""
    offers: List[Offer] = []
    seen_offer_keys: set[Tuple[object, ...]] = set()

    for keyword in watch_item.match_keywords:
        normalised_keyword = _normalise_keyword_for_search(keyword)
        for offer in offers_by_keyword.get(normalised_keyword, []):
            if offer.store not in watch_item.stores:
                continue
            offer_key = (
                offer.store,
                (offer.barcode or "").lower(),
                offer.product_title.strip().lower(),
                (offer.size or "").strip().lower(),
                round(offer.price, 2),
                offer.url.strip().lower(),
            )
            if offer_key in seen_offer_keys:
                continue
            seen_offer_keys.add(offer_key)
            offers.append(
                Offer(
                    watch_name=watch_item.name,
                    store=offer.store,
                    product_title=offer.product_title,
                    brand=offer.brand,
                    price=offer.price,
                    size=offer.size,
                    url=offer.url,
                    barcode=offer.barcode,
                    was_price=offer.was_price,
                    is_half_price=offer.is_half_price,
                )
            )

    if watch_item.exclude_keywords:
        offers = [
            offer
            for offer in offers
            if not any(
                _keyword_matches_offer(exclude_keyword, offer)
                for exclude_keyword in watch_item.exclude_keywords
            )
        ]

    offers = [
        offer
        for offer in offers
        if any(
            _keyword_matches_offer(match_keyword, offer)
            for match_keyword in watch_item.match_keywords
        )
    ]

    if watch_item.only_half_price:
        offers = [
            offer
            for offer in offers
            if offer.is_half_price
            or (watch_item.include_unknown_half_price and offer.was_price is None)
        ]

    return offers


def build_report(
    all_offers: Dict[str, List[Offer]],
    limit_warnings: Optional[List[str]] = None,
) -> str:
    """Render a text report plus optional API usage warnings."""
    lines: List[str] = []

    if limit_warnings:
        lines.append("## API usage warnings")
        for msg in limit_warnings:
            lines.append(f"- {msg}")
        lines.append("")

    for watch_name, offers in all_offers.items():
        lines.append(f"## {watch_name}")
        if not offers:
            lines.append("No matching products or specials found.\n")
            continue

        offers_sorted = sorted(offers, key=lambda offer: (offer.store, offer.price))

        cheapest_by_store: Dict[str, Offer] = {}
        for offer in offers_sorted:
            if (
                offer.store not in cheapest_by_store
                or offer.price < cheapest_by_store[offer.store].price
            ):
                cheapest_by_store[offer.store] = offer

        for offer in offers_sorted:
            was_str = f" (was ${offer.was_price:.2f})" if offer.was_price else ""
            half_str = " [HALF PRICE?]" if offer.is_half_price else ""
            brand_str = f" - {offer.brand}" if offer.brand else ""
            size_str = f" - {offer.size}" if offer.size else ""
            barcode_str = f" - barcode {offer.barcode}" if offer.barcode else ""
            url_str = f" - {offer.url}" if offer.url else ""
            lines.append(
                f"- {offer.store}: {offer.product_title}{brand_str} - "
                f"${offer.price:.2f}{was_str}{half_str}{size_str}"
                f"{barcode_str}{url_str}"
            )

        if len(cheapest_by_store) >= 2:
            cheapest = min(cheapest_by_store.values(), key=lambda offer: offer.price)
            lines.append(
                f"**Cheapest overall:** {cheapest.store} at ${cheapest.price:.2f}"
            )

        lines.append("")

    return "\n".join(lines)


# =========================
# EMAIL SENDER (GMAIL)
# =========================


def send_email_report(report: str, subject: str = "Weekly grocery specials report"):
    """Send the report via SMTP using the configured auth settings."""
    email_config_path, cfg = load_email_config()
    if email_config_path is None:
        print(
            "[WARN] No email config found. Expected config/email_config.yaml "
            "or email_config.yaml; skipping email send."
        )
        return

    gmail_user = cfg["gmail_user"]
    auth_mode = str(cfg.get("auth_mode", "app_password")).strip().lower()
    if auth_mode not in {"app_password", "password"}:
        raise ValueError(
            f"{email_config_path} auth_mode must be 'app_password' or 'password'"
        )

    password_key = (
        "gmail_app_password" if auth_mode == "app_password" else "gmail_password"
    )
    gmail_password = cfg.get(password_key)
    if not gmail_password:
        raise ValueError(
            f"{email_config_path} must define {password_key} when auth_mode is "
            f"'{auth_mode}'"
        )

    to_email = cfg.get("to_email", gmail_user)
    smtp_host = str(cfg.get("smtp_host", "smtp.gmail.com")).strip()
    smtp_port = int(cfg.get("smtp_port", 587))
    smtp_use_tls = bool(cfg.get("smtp_use_tls", True))
    email_subject = str(cfg.get("email_subject", subject)).strip() or subject

    msg = EmailMessage()
    msg["Subject"] = email_subject
    msg["From"] = gmail_user
    msg["To"] = to_email
    msg.set_content(report)

    context = ssl.create_default_context() if smtp_use_tls else None
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if smtp_use_tls:
            server.starttls(context=context)
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
    print(f"[INFO] Report emailed to {to_email}")


def build_email_test_report() -> str:
    """Return a small sample report for email configuration testing."""
    return "\n".join(
        [
            "## Email Test",
            "This is a sample specials report used to verify email delivery.",
            "",
            "## Sample Item",
            (
                "- Coles: Example Product - Example Brand - $4.50 - "
                "https://example.com/coles"
            ),
            (
                "- Woolworths: Example Product - Example Brand - $4.80 - "
                "barcode 1234567890 - https://example.com/woolworths"
            ),
            "",
            "If you received this email, the email configuration is working.",
        ]
    )


# =========================
# TEST / DEBUG HELPERS
# =========================


def pretty_print_sample(data: dict, max_items: int = 3):
    """Print top-level keys and a few product entries for debugging."""
    if isinstance(data, dict):
        print("Top-level keys:", list(data.keys()))
        current_page, total_pages, total_results = extract_pagination_from_response(
            data
        )
        print(
            "Pagination:",
            {
                "current_page": current_page,
                "total_pages": total_pages,
                "total_results": total_results,
            },
        )
    else:
        print("Top-level type:", type(data))

    products = extract_products_from_response(data)
    print(f"Detected {len(products)} product(s)")
    for i, product in enumerate(products[:max_items]):
        print(f"\n--- Product #{i + 1} ---")
        print(json.dumps(product, indent=2, sort_keys=True))


def run_test_coles(keyword: str):
    """Print a sample Coles product-search response."""
    print(f"[TEST] Coles product search for: {keyword!r}")
    try:
        data = search_coles(keyword)
        pretty_print_sample(data)
    except requests.HTTPError as exc:
        response = exc.response
        print(
            f"[ERROR] Coles request failed with HTTP {response.status_code}: "
            f"{response.url}"
        )
        if response.text:
            print(response.text[:2000])
    except Exception as exc:
        print(f"[ERROR] Coles test failed: {exc}")


def run_test_woolies(keyword: str):
    """Print a sample Woolworths product-search response."""
    print(f"[TEST] Woolworths product search for: {keyword!r}")
    try:
        data = search_woolies(keyword)
        pretty_print_sample(data)
    except requests.HTTPError as exc:
        response = exc.response
        print(
            f"[ERROR] Woolworths request failed with HTTP {response.status_code}: "
            f"{response.url}"
        )
        if response.text:
            print(response.text[:2000])
    except Exception as exc:
        print(f"[ERROR] Woolworths test failed: {exc}")


# =========================
# ENTRY POINT
# =========================


def main(send_email: bool = True, testing_mode: bool = False):
    """Run the full flow: load watchlist, fetch offers, report, email."""
    RUN_API_CALL_COUNT["Coles"] = 0
    RUN_API_CALL_COUNT["Woolworths"] = 0
    watchlist = load_watchlist("watchlist.yaml")
    all_offers: Dict[str, List[Offer]] = {}

    limit_error: Optional[str] = None
    try:
        offers_by_keyword = collect_offers_by_keyword(watchlist)
        for watch_item in watchlist:
            all_offers[watch_item.name] = find_offers_for_watch_item(
                watch_item, offers_by_keyword
            )
    except APILimitExceeded as exc:
        limit_error = str(exc)
        _record_limit_warning(limit_error)
        print(f"[ERROR] {limit_error}")

    report = build_report(all_offers, limit_warnings=LIMIT_WARNINGS)
    print(report)

    if testing_mode:
        print("[INFO] Testing mode: email send skipped.")
        print(
            "[INFO] API calls this run - Coles: "
            f"{RUN_API_CALL_COUNT.get('Coles', 0)}, "
            "Woolworths: "
            f"{RUN_API_CALL_COUNT.get('Woolworths', 0)}"
        )
        print(
            "[INFO] API calls this month - Coles: "
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
        help="Test the Coles product-search API and print sample products.",
    )
    parser.add_argument(
        "--test-woolies",
        metavar="KEYWORD",
        help="Test the Woolworths product-search API and print sample products.",
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
    parser.add_argument(
        "--test-email",
        action="store_true",
        help="Send a sample email report without calling the product APIs.",
    )

    args = parser.parse_args()

    if args.test_email:
        _, email_cfg = load_email_config()
        send_email_report(
            build_email_test_report(),
            subject=str(
                email_cfg.get(
                    "email_test_subject",
                    "Email test - grocery specials checker",
                )
            ),
        )
    elif args.test_coles:
        run_test_coles(args.test_coles)
    elif args.test_woolies:
        run_test_woolies(args.test_woolies)
    else:
        suppress_email = args.no_email or args.testing
        main(send_email=not suppress_email, testing_mode=args.testing)
