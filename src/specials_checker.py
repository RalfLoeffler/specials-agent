from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
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
SPECIALS_FRESHNESS_CONFIG_PATH = os.path.join("config", "specials_freshness.yaml")
VENDOR_SPECIALS_STATE_PATH = os.path.join("config", "vendor_specials_state.json")
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
STORE_NAMES = ("Coles", "Woolworths")
WEEKDAY_NAME_TO_INT = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


@dataclass
class VendorScheduleWindow:
    start_day: int
    force_send_day: int


@dataclass
class VendorProcessingPlan:
    schedule: VendorScheduleWindow
    should_query: bool
    within_window: bool


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


def _normalise_vendor_key(value: object) -> Optional[str]:
    """Normalise config keys like 'coles' and 'woolies' to store names."""
    if value is None:
        return None
    text = str(value).strip().lower()
    alias_map = {
        "coles": "Coles",
        "woolworths": "Woolworths",
        "woolies": "Woolworths",
    }
    return alias_map.get(text)


def _coerce_weekday(value: object, field_name: str, default: int) -> int:
    """Parse weekday names or integers into Python weekday indices."""
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        day = int(value)
        if 0 <= day <= 6:
            return day
        raise ValueError(f"{field_name} must be between 0 (Mon) and 6 (Sun)")

    key = str(value).strip().lower()
    mapped = WEEKDAY_NAME_TO_INT.get(key)
    if mapped is None:
        raise ValueError(
            f"{field_name} must be a weekday name (e.g. Wednesday) or 0-6"
        )
    return mapped


def _coerce_day_distance(start_day: int, end_day: int) -> int:
    """Return forward distance in days in a weekly cycle."""
    return (end_day - start_day) % 7


def _is_weekday_in_window(weekday: int, start_day: int, end_day: int) -> bool:
    """Return True when weekday is inside a start->end weekly window."""
    to_target = (weekday - start_day) % 7
    to_end = _coerce_day_distance(start_day, end_day)
    return to_target <= to_end


def _cycle_anchor_for_day(today: date, start_day: int) -> date:
    """Return the most recent start-day date at or before today."""
    return today - timedelta(days=(today.weekday() - start_day) % 7)


def _default_vendor_state() -> Dict[str, Any]:
    """Create a blank persisted state payload for one vendor."""
    return {
        "cycle_anchor": None,
        "reference_hash": None,
        "last_known_hash": None,
        "changed_this_cycle": False,
        "sent_this_cycle": False,
        "last_checked_date": None,
        "last_sent_date": None,
    }


def _load_vendor_specials_state() -> Dict[str, Dict[str, Any]]:
    """Load persisted per-vendor freshness state from config."""
    state: Dict[str, Dict[str, Any]] = {
        store: _default_vendor_state() for store in STORE_NAMES
    }
    if not os.path.exists(VENDOR_SPECIALS_STATE_PATH):
        return state

    try:
        with open(VENDOR_SPECIALS_STATE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return state

    vendors_raw = raw.get("vendors", {}) if isinstance(raw, dict) else {}
    if not isinstance(vendors_raw, dict):
        return state

    for key, vendor_payload in vendors_raw.items():
        vendor = _normalise_vendor_key(key)
        if vendor is None or not isinstance(vendor_payload, dict):
            continue
        merged = _default_vendor_state()
        merged.update(vendor_payload)
        state[vendor] = merged
    return state


def _save_vendor_specials_state(state: Dict[str, Dict[str, Any]]) -> None:
    """Persist per-vendor freshness state to config."""
    os.makedirs(os.path.dirname(VENDOR_SPECIALS_STATE_PATH), exist_ok=True)
    payload = {
        "vendors": {store: state.get(store, _default_vendor_state()) for store in STORE_NAMES}
    }
    with open(VENDOR_SPECIALS_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _load_specials_freshness_config() -> Dict[str, Any]:
    """Load optional config controlling freshness schedules and email text."""
    defaults = {
        "vendors": {
            "default": {
                "start_day": "Wednesday",
                "force_send_day": "Saturday",
            }
        },
        "email": {
            "success_subject": None,
            "success_preamble": "",
            "no_new_data_subject": "No new specials data for {vendor}",
            "no_new_data_preamble": (
                "No new API specials data was detected for {vendor} yet; retrying on "
                "the next configured run day."
            ),
            "forced_send_subject": "Saturday fallback specials for {vendor}",
            "forced_send_preamble": (
                "No new API specials data was detected for {vendor} by the configured "
                "fallback day, so this report is sent anyway."
            ),
        },
    }
    if not os.path.exists(SPECIALS_FRESHNESS_CONFIG_PATH):
        return defaults

    with open(SPECIALS_FRESHNESS_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        return defaults

    merged = {
        "vendors": dict(defaults["vendors"]),
        "email": dict(defaults["email"]),
    }

    vendors_raw = raw.get("vendors")
    if isinstance(vendors_raw, dict):
        for key, value in vendors_raw.items():
            if not isinstance(value, dict):
                continue
            if str(key).strip().lower() == "default":
                merged["vendors"]["default"].update(value)
                continue
            vendor = _normalise_vendor_key(key)
            if vendor:
                merged["vendors"][vendor] = value

    email_raw = raw.get("email")
    if isinstance(email_raw, dict):
        merged["email"].update(email_raw)

    return merged


def _resolve_vendor_schedule(
    config: Dict[str, Any],
    vendor: str,
) -> VendorScheduleWindow:
    """Resolve effective start and force-send weekdays for one vendor."""
    vendors_cfg = config.get("vendors", {}) if isinstance(config, dict) else {}
    default_cfg = vendors_cfg.get("default", {}) if isinstance(vendors_cfg, dict) else {}
    vendor_cfg = vendors_cfg.get(vendor, {}) if isinstance(vendors_cfg, dict) else {}
    start_day = _coerce_weekday(
        vendor_cfg.get("start_day", default_cfg.get("start_day")),
        field_name=f"{vendor} start_day",
        default=2,
    )
    force_send_day = _coerce_weekday(
        vendor_cfg.get("force_send_day", default_cfg.get("force_send_day")),
        field_name=f"{vendor} force_send_day",
        default=5,
    )
    return VendorScheduleWindow(start_day=start_day, force_send_day=force_send_day)


def _prepare_vendor_processing_plans(
    freshness_config: Dict[str, Any],
    state: Dict[str, Dict[str, Any]],
    today: date,
) -> Dict[str, VendorProcessingPlan]:
    """Build per-vendor query plans, resetting cycle state when required."""
    plans: Dict[str, VendorProcessingPlan] = {}
    for vendor in STORE_NAMES:
        vendor_state = state.setdefault(vendor, _default_vendor_state())
        schedule = _resolve_vendor_schedule(freshness_config, vendor)
        anchor_date = _cycle_anchor_for_day(today, schedule.start_day)
        anchor_key = anchor_date.isoformat()

        if vendor_state.get("cycle_anchor") != anchor_key:
            vendor_state["cycle_anchor"] = anchor_key
            vendor_state["reference_hash"] = vendor_state.get("last_known_hash")
            vendor_state["changed_this_cycle"] = False
            vendor_state["sent_this_cycle"] = False

        within_window = _is_weekday_in_window(
            today.weekday(),
            schedule.start_day,
            schedule.force_send_day,
        )
        already_completed = bool(
            vendor_state.get("changed_this_cycle") and vendor_state.get("sent_this_cycle")
        )
        plans[vendor] = VendorProcessingPlan(
            schedule=schedule,
            should_query=within_window and not already_completed,
            within_window=within_window,
        )

    return plans


def _build_vendor_offers_view(
    all_offers: Dict[str, List[Offer]],
    vendor: str,
    allowed_watch_names: Optional[set[str]] = None,
) -> Dict[str, List[Offer]]:
    """Return offers filtered to one vendor while preserving watchlist keys."""
    filtered: Dict[str, List[Offer]] = {}
    for watch_name, offers in all_offers.items():
        if allowed_watch_names is not None and watch_name not in allowed_watch_names:
            continue
        filtered[watch_name] = [offer for offer in offers if offer.store == vendor]
    return filtered


def _vendor_offer_signature(vendor_offers: Dict[str, List[Offer]]) -> str:
    """Build a stable checksum used to detect specials changes per vendor."""
    payload: List[Dict[str, Any]] = []
    for watch_name in sorted(vendor_offers.keys()):
        offers = vendor_offers[watch_name]
        serialised_offers: List[Dict[str, Any]] = []
        for offer in sorted(
            offers,
            key=lambda item: (
                item.store,
                item.product_title,
                item.brand or "",
                item.size or "",
                round(item.price, 2),
                item.url or "",
                item.barcode or "",
                round(item.was_price, 2) if item.was_price is not None else -1,
            ),
        ):
            serialised_offers.append(
                {
                    "store": offer.store,
                    "product_title": offer.product_title,
                    "brand": offer.brand,
                    "price": round(offer.price, 2),
                    "size": offer.size,
                    "url": offer.url,
                    "barcode": offer.barcode,
                    "was_price": (
                        round(offer.was_price, 2)
                        if offer.was_price is not None
                        else None
                    ),
                }
            )
        payload.append({"watch_name": watch_name, "offers": serialised_offers})

    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _render_template(
    value: object,
    fallback: str,
    **context: str,
) -> str:
    """Render a configurable template with format placeholders."""
    template = str(value if value not in (None, "") else fallback)
    try:
        return template.format(**context)
    except Exception:
        return template


def _prepend_preamble(report: str, preamble: str) -> str:
    """Prefix plain-text report body with a configured preamble."""
    preamble_text = (preamble or "").strip()
    if not preamble_text:
        return report
    return "\n\n".join([preamble_text, report])


def _prepend_preamble_html(html_report: str, preamble: str) -> str:
    """Prefix HTML report body with a paragraph preamble."""
    preamble_text = (preamble or "").strip()
    if not preamble_text:
        return html_report
    prefix = f"<p>{html.escape(preamble_text)}</p>"
    opening = '<html><body style="font-family: Arial, sans-serif; color: #222;">'
    if html_report.startswith(opening):
        return opening + prefix + html_report[len(opening):]
    return prefix + html_report


def _format_vendor_list(vendors: List[str]) -> str:
    """Format vendor names for subject/preamble placeholders."""
    if not vendors:
        return ""
    if len(vendors) == 1:
        return vendors[0]
    if len(vendors) == 2:
        return f"{vendors[0]} and {vendors[1]}"
    return ", ".join(vendors[:-1]) + f", and {vendors[-1]}"


def _status_label(mode: str) -> str:
    """Map internal mode values to stable template-facing labels."""
    labels = {
        "success": "new_data",
        "forced_send": "forced_send",
        "no_new_data": "no_new_data",
    }
    return labels.get(mode, mode)


def _build_vendor_mode_summary(vendor_modes: Dict[str, str]) -> str:
    """Return a compact human-readable per-vendor mode summary."""
    parts = [
        f"{vendor}: {_status_label(mode)}"
        for vendor, mode in sorted(vendor_modes.items())
    ]
    return "; ".join(parts)


def _build_run_subject_and_preamble(
    email_cfg: Dict[str, Any],
    freshness_config: Dict[str, Any],
    vendor_modes: Dict[str, str],
) -> Tuple[str, str]:
    """Resolve subject/preamble for one run that may include multiple vendors."""
    email_cfg_subject = str(
        email_cfg.get("email_subject", "Weekly grocery specials report")
    ).strip() or "Weekly grocery specials report"
    email_cfg_preamble = str(email_cfg.get("email_preamble", "")).strip()

    freshness_email = (
        freshness_config.get("email", {})
        if isinstance(freshness_config, dict)
        else {}
    )
    if not isinstance(freshness_email, dict):
        freshness_email = {}

    vendors = sorted(vendor_modes.keys())
    vendor_text = _format_vendor_list(vendors)
    mode_values = set(vendor_modes.values())
    mode = next(iter(mode_values)) if len(mode_values) == 1 else "mixed"
    context = {
        "vendor": vendor_text,
        "vendors": vendor_text,
        "vendor_summary": _build_vendor_mode_summary(vendor_modes),
    }

    if mode == "mixed":
        subject = _render_template(
            freshness_email.get("mixed_subject"),
            fallback="Specials update ({vendor_summary})",
            **context,
        )
        preamble = _render_template(
            freshness_email.get("mixed_preamble"),
            fallback=(
                "This run contains mixed vendor freshness states: "
                "{vendor_summary}."
            ),
            **context,
        )
        return subject, preamble

    if mode == "success":
        subject = _render_template(
            freshness_email.get("success_subject"),
            fallback=email_cfg_subject,
            **context,
        )
        preamble = _render_template(
            freshness_email.get("success_preamble"),
            fallback=email_cfg_preamble,
            **context,
        )
        return subject, preamble

    if mode == "forced_send":
        no_new = _render_template(
            freshness_email.get("no_new_data_preamble"),
            fallback="No new specials data was detected for {vendor}.",
            **context,
        )
        forced = _render_template(
            freshness_email.get("forced_send_preamble"),
            fallback=(
                "This is the configured fallback send day, so the report is sent "
                "anyway."
            ),
            **context,
        )
        subject = _render_template(
            freshness_email.get("forced_send_subject"),
            fallback="Saturday fallback specials for {vendor}",
            **context,
        )
        preamble = " ".join(part for part in [no_new.strip(), forced.strip()] if part)
        return subject, preamble

    subject = _render_template(
        freshness_email.get("no_new_data_subject"),
        fallback="No new specials data for {vendor}",
        **context,
    )
    preamble = _render_template(
        freshness_email.get("no_new_data_preamble"),
        fallback="No new API specials data was detected for {vendor}.",
        **context,
    )
    return subject, preamble


# =========================
# DATA MODELS
# =========================


@dataclass
class WatchItem:
    name: str
    match_keywords: List[str]
    include_keywords: List[str]
    exclude_keywords: List[str]
    stores: List[str]
    include_unknown_half_price: bool = True
    only_half_price: bool = False
    email_indices: Optional[List[int]] = None
    price_range: Optional[str] = None
    size_range: Optional[str] = None


@dataclass
class NumericFilter:
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    include_minimum: bool = True
    include_maximum: bool = True


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
                include_keywords=list(
                    raw.get("include_keywords", raw["match_keywords"])
                ),
                exclude_keywords=list(raw.get("exclude_keywords", [])),
                stores=_normalise_watch_stores(raw.get("stores")),
                include_unknown_half_price=bool(
                    raw.get("include_unknown_half_price", True)
                ),
                only_half_price=bool(raw.get("only_half_price", False)),
                email_indices=_normalise_email_indices(
                    raw.get("email_indices", raw.get("email_index"))
                ),
                price_range=_normalise_numeric_filter_input(
                    raw.get("price_range"),
                    field_name="price_range",
                ),
                size_range=_normalise_numeric_filter_input(
                    raw.get("size_range"),
                    field_name="size_range",
                ),
            )
        )
    return items


def _normalise_email_indices(value: object) -> Optional[List[int]]:
    """Normalise optional email recipient index selectors from YAML."""
    if value in (None, ""):
        return None

    raw_values = value if isinstance(value, list) else [value]
    indices: List[int] = []
    for raw_value in raw_values:
        try:
            index = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "watchlist email_index/email_indices values must be integers"
            ) from exc
        if index < 0:
            raise ValueError(
                "watchlist email_index/email_indices values must be zero or greater"
            )
        if index not in indices:
            indices.append(index)

    return indices or None


def get_email_recipients(cfg: Dict[str, Any]) -> List[str]:
    """Return the configured recipient list in index order."""
    recipients_raw = cfg.get("to_emails")
    recipients: List[str] = []
    if recipients_raw not in (None, ""):
        if not isinstance(recipients_raw, list):
            raise ValueError("email_config to_emails must be a list of addresses")
        for entry in recipients_raw:
            text = str(entry).strip()
            if text and text not in recipients:
                recipients.append(text)
    else:
        primary = str(cfg.get("to_email", cfg.get("gmail_user", ""))).strip()
        if primary:
            recipients.append(primary)

    return recipients


def get_email_bool_option(
    cfg: Dict[str, Any],
    key: str,
    recipient_index: int,
    default: bool = False,
) -> bool:
    """Return a per-recipient email boolean option from scalar or list config."""
    raw_value = cfg.get(key, default)
    if isinstance(raw_value, list):
        if recipient_index < len(raw_value):
            return _coerce_bool(raw_value[recipient_index], default=default)
        return default
    return _coerce_bool(raw_value, default=default)


def validate_watchlist_email_indices(
    watchlist: List[WatchItem], recipients: List[str]
) -> None:
    """Ensure watchlist email indices point at configured recipients."""
    if not recipients:
        return

    max_index = len(recipients) - 1
    for watch_item in watchlist:
        if not watch_item.email_indices:
            continue
        for index in watch_item.email_indices:
            if index > max_index:
                raise ValueError(
                    "watchlist item "
                    f"{watch_item.name!r} references email index {index}, "
                    f"but only indices 0..{max_index} exist in email_config.yaml"
                )


def select_offers_for_email_recipient(
    watchlist: List[WatchItem],
    all_offers: Dict[str, List[Offer]],
    recipient_index: int,
) -> Dict[str, List[Offer]]:
    """Return the watchlist subset intended for one recipient."""
    selected: Dict[str, List[Offer]] = {}
    for watch_item in watchlist:
        if watch_item.email_indices and recipient_index not in watch_item.email_indices:
            continue
        selected[watch_item.name] = all_offers.get(watch_item.name, [])
    return selected


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


def _coerce_bool(value: object, default: bool = False) -> bool:
    """Parse common config-style boolean values."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalise_numeric_filter_input(
    value: object,
    field_name: str,
) -> Optional[str]:
    """Normalise a numeric filter input from YAML into a compact string."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return str(value)

    text = str(value).strip()
    if not text:
        return None

    _parse_numeric_filter_spec(text, field_name=field_name)
    return text


def _parse_numeric_filter_spec(
    value: str,
    field_name: str,
) -> NumericFilter:
    """Parse one numeric filter expression such as 800-1000 or <1.50."""
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be blank")

    comparison_match = re.fullmatch(r"(<=|>=|<|>)\s*(\d+(?:\.\d+)?)", text)
    if comparison_match:
        operator, number_text = comparison_match.groups()
        number = float(number_text)
        if operator == "<":
            return NumericFilter(maximum=number, include_maximum=False)
        if operator == "<=":
            return NumericFilter(maximum=number, include_maximum=True)
        if operator == ">":
            return NumericFilter(minimum=number, include_minimum=False)
        return NumericFilter(minimum=number, include_minimum=True)

    range_match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)",
        text,
    )
    if range_match:
        minimum_text, maximum_text = range_match.groups()
        minimum = float(minimum_text)
        maximum = float(maximum_text)
        if minimum > maximum:
            raise ValueError(
                f"{field_name} range minimum must be less than or equal to maximum"
            )
        return NumericFilter(minimum=minimum, maximum=maximum)

    exact_match = re.fullmatch(r"\d+(?:\.\d+)?", text)
    if exact_match:
        number = float(text)
        return NumericFilter(minimum=number, maximum=number)

    raise ValueError(
        f"{field_name} must be numeric-only input like 900, 800-1000, or <1.50"
    )


def _extract_numeric_value(value: object) -> Optional[float]:
    """Extract the first numeric value from a scalar such as $1.50 or 900ml."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def _numeric_filter_matches(
    raw_value: object,
    filter_spec: Optional[str],
    field_name: str,
) -> bool:
    """Return True when a value passes the configured numeric filter."""
    if not filter_spec:
        return True

    numeric_value = _extract_numeric_value(raw_value)
    if numeric_value is None:
        return False

    numeric_filter = _parse_numeric_filter_spec(filter_spec, field_name=field_name)

    if numeric_filter.minimum is not None:
        if numeric_filter.include_minimum:
            if numeric_value < numeric_filter.minimum:
                return False
        elif numeric_value <= numeric_filter.minimum:
            return False

    if numeric_filter.maximum is not None:
        if numeric_filter.include_maximum:
            if numeric_value > numeric_filter.maximum:
                return False
        elif numeric_value >= numeric_filter.maximum:
            return False

    return True


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
    size = _coerce_str(
        _pick_first(
            raw,
            "product_size",
            "productSize",
            "ProductSize",
            "size",
            "Size",
            "packageSize",
            "PackageSize",
        )
    )
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
    size = _coerce_str(
        _pick_first(
            raw,
            "product_size",
            "productSize",
            "ProductSize",
            "size",
            "Size",
            "packageSize",
            "PackageSize",
        )
    )
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
        if value.strip().lower() == "none":
            return []
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


def collect_offers_by_keyword(
    watchlist: List[WatchItem],
    allowed_stores: Optional[set[str]] = None,
) -> Dict[str, List[Offer]]:
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
            allowed_item_stores = set(watch_item.stores)
            if allowed_stores is not None:
                allowed_item_stores = allowed_item_stores.intersection(allowed_stores)
            keyword_stores.setdefault(normalised_keyword, set()).update(
                allowed_item_stores
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
                            include_keywords=[keyword],
                            exclude_keywords=[],
                            stores=[store],
                            include_unknown_half_price=True,
                            only_half_price=False,
                            price_range=None,
                            size_range=None,
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

    include_keywords = watch_item.include_keywords or watch_item.match_keywords

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
            _keyword_matches_offer(include_keyword, offer)
            for include_keyword in include_keywords
        )
    ]

    if watch_item.only_half_price:
        offers = [
            offer
            for offer in offers
            if offer.is_half_price
            or (watch_item.include_unknown_half_price and offer.was_price is None)
        ]

    if watch_item.price_range:
        offers = [
            offer
            for offer in offers
            if _numeric_filter_matches(
                offer.price,
                watch_item.price_range,
                field_name="price_range",
            )
        ]

    if watch_item.size_range:
        offers = [
            offer
            for offer in offers
            if _numeric_filter_matches(
                offer.size,
                watch_item.size_range,
                field_name="size_range",
            )
        ]

    return offers


def build_report(
    all_offers: Dict[str, List[Offer]],
    limit_warnings: Optional[List[str]] = None,
    verbose: bool = False,
    api_calls_footer: Optional[str] = None,
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
            barcode_str = (
                f" - barcode {offer.barcode}" if verbose and offer.barcode else ""
            )
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

    if api_calls_footer:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("## Accumulated API calls")
        lines.extend(api_calls_footer.splitlines())

    return "\n".join(lines)


def build_html_report(
    all_offers: Dict[str, List[Offer]],
    limit_warnings: Optional[List[str]] = None,
    verbose: bool = False,
    api_calls_footer: Optional[str] = None,
) -> str:
    """Render the report as HTML tables for email clients."""
    parts: List[str] = [
        '<html><body style="font-family: Arial, sans-serif; color: #222;">'
    ]

    if limit_warnings:
        parts.append("<h2>API usage warnings</h2><ul>")
        for msg in limit_warnings:
            parts.append(f"<li>{html.escape(msg)}</li>")
        parts.append("</ul>")

    for watch_name, offers in all_offers.items():
        parts.append(f"<h2>{html.escape(watch_name)}</h2>")
        if not offers:
            parts.append("<p>No matching products or specials found.</p>")
            continue

        offers_sorted = sorted(offers, key=lambda offer: (offer.store, offer.price))
        cheapest_by_store: Dict[str, Offer] = {}
        for offer in offers_sorted:
            if (
                offer.store not in cheapest_by_store
                or offer.price < cheapest_by_store[offer.store].price
            ):
                cheapest_by_store[offer.store] = offer

        headers = ["Store", "Product", "Brand", "Price", "Size", "Link"]
        if verbose:
            headers.extend(["Was Price", "Barcode"])

        parts.append(
            '<table style="border-collapse: collapse; width: 100%; '
            'margin-bottom: 16px;">'
        )
        parts.append("<thead><tr>")
        for header in headers:
            parts.append(
                '<th style="border: 1px solid #ccc; background: #f5f5f5; '
                'padding: 8px; text-align: left;">'
                f"{html.escape(header)}</th>"
            )
        parts.append("</tr></thead><tbody>")

        for offer in offers_sorted:
            price_text = f"${offer.price:.2f}"
            if offer.is_half_price:
                price_text += " (half price)"

            link_html = (
                f'<a href="{html.escape(offer.url, quote=True)}">Open</a>'
                if offer.url
                else ""
            )

            cells = [
                html.escape(offer.store),
                html.escape(offer.product_title),
                html.escape(offer.brand or ""),
                html.escape(price_text),
                html.escape(offer.size or ""),
                link_html,
            ]
            if verbose:
                cells.extend(
                    [
                        html.escape(
                            f"${offer.was_price:.2f}" if offer.was_price else ""
                        ),
                        html.escape(offer.barcode or ""),
                    ]
                )

            parts.append("<tr>")
            for cell in cells:
                parts.append(
                    '<td style="border: 1px solid #ccc; padding: 8px; '
                    'vertical-align: top;">'
                    f"{cell}</td>"
                )
            parts.append("</tr>")

        parts.append("</tbody></table>")

        if len(cheapest_by_store) >= 2:
            cheapest = min(cheapest_by_store.values(), key=lambda offer: offer.price)
            parts.append(
                "<p><strong>Cheapest overall:</strong> "
                f"{html.escape(cheapest.store)} at ${cheapest.price:.2f}</p>"
            )

    if api_calls_footer:
        parts.append("<h2>Accumulated API calls</h2><ul>")
        for line in api_calls_footer.splitlines():
            parts.append(f"<li>{html.escape(line.lstrip('- ').strip())}</li>")
        parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)


def build_api_calls_footer() -> str:
    """Return the accumulated monthly API call summary for email footers."""
    return "\n".join(
        [
            f"- Coles this month: {API_CALL_COUNT.get('Coles', 0)}",
            f"- Woolworths this month: {API_CALL_COUNT.get('Woolworths', 0)}",
        ]
    )


def append_api_calls_footer(report: str, api_calls_footer: Optional[str]) -> str:
    """Append the optional API call footer to a plain-text report."""
    if not api_calls_footer:
        return report
    return "\n\n".join([report.rstrip(), "## Accumulated API calls", api_calls_footer])


def append_api_calls_footer_html(
    html_report: str, api_calls_footer: Optional[str]
) -> str:
    """Append the optional API call footer to an HTML report."""
    if not api_calls_footer:
        return html_report

    footer_parts = ["<h2>Accumulated API calls</h2><ul>"]
    for line in api_calls_footer.splitlines():
        footer_parts.append(f"<li>{html.escape(line.lstrip('- ').strip())}</li>")
    footer_parts.append("</ul>")
    footer_html = "".join(footer_parts)

    closing_tag = "</body></html>"
    if html_report.endswith(closing_tag):
        return html_report[: -len(closing_tag)] + footer_html + closing_tag
    return html_report + footer_html


def resolve_email_subject(cfg: Dict[str, Any], subject: str) -> str:
    """Resolve the effective email subject with config fallback."""
    email_subject = str(subject).strip() or "Weekly grocery specials report"
    if email_subject == "Weekly grocery specials report":
        email_subject = (
            str(cfg.get("email_subject", email_subject)).strip() or email_subject
        )
    return email_subject


def build_email_deliveries(
    watchlist: List[WatchItem],
    all_offers: Dict[str, List[Offer]],
    email_cfg: Dict[str, Any],
    subject: str = "Weekly grocery specials report",
) -> List[Dict[str, Any]]:
    """Build per-recipient email payloads using the configured routing rules."""
    recipients = get_email_recipients(email_cfg)
    deliveries: List[Dict[str, Any]] = []

    if recipients:
        for recipient_index, recipient in enumerate(recipients):
            recipient_offers = select_offers_for_email_recipient(
                watchlist,
                all_offers,
                recipient_index,
            )
            if not recipient_offers:
                continue

            report_verbose = get_email_bool_option(
                email_cfg,
                "report_verbose",
                recipient_index,
                default=False,
            )
            api_calls_footer = (
                build_api_calls_footer()
                if get_email_bool_option(
                    email_cfg,
                    "report_calls",
                    recipient_index,
                    default=False,
                )
                else None
            )
            deliveries.append(
                {
                    "recipient_index": recipient_index,
                    "recipient": recipient,
                    "subject": resolve_email_subject(email_cfg, subject),
                    "verbose": report_verbose,
                    "report_calls": bool(api_calls_footer),
                    "watch_names": list(recipient_offers.keys()),
                    "report": build_report(
                        recipient_offers,
                        limit_warnings=LIMIT_WARNINGS,
                        verbose=report_verbose,
                        api_calls_footer=api_calls_footer,
                    ),
                    "html_report": build_html_report(
                        recipient_offers,
                        limit_warnings=LIMIT_WARNINGS,
                        verbose=report_verbose,
                        api_calls_footer=api_calls_footer,
                    ),
                }
            )
        return deliveries

    default_api_calls_footer = (
        build_api_calls_footer()
        if get_email_bool_option(email_cfg, "report_calls", 0, default=False)
        else None
    )
    default_report_verbose = get_email_bool_option(
        email_cfg,
        "report_verbose",
        0,
        default=False,
    )
    fallback_recipient = (
        str(email_cfg.get("to_email", email_cfg.get("gmail_user", ""))).strip()
        or "(no recipient configured)"
    )
    deliveries.append(
        {
            "recipient_index": 0,
            "recipient": fallback_recipient,
            "subject": resolve_email_subject(email_cfg, subject),
            "verbose": default_report_verbose,
            "report_calls": bool(default_api_calls_footer),
            "watch_names": list(all_offers.keys()),
            "report": build_report(
                all_offers,
                limit_warnings=LIMIT_WARNINGS,
                verbose=default_report_verbose,
                api_calls_footer=default_api_calls_footer,
            ),
            "html_report": build_html_report(
                all_offers,
                limit_warnings=LIMIT_WARNINGS,
                verbose=default_report_verbose,
                api_calls_footer=default_api_calls_footer,
            ),
        }
    )
    return deliveries


def print_email_delivery_preview(deliveries: List[Dict[str, Any]]) -> None:
    """Print a dry-run preview of each email that would be sent."""
    if not deliveries:
        print("[INFO] No email deliveries were generated for preview.")
        return

    print("[INFO] Email delivery preview:")
    for delivery in deliveries:
        print("")
        print(
            "[INFO] ------------------------------------------------------------"
        )
        print(
            f"[INFO] Recipient #{delivery['recipient_index']}: "
            f"{delivery['recipient']}"
        )
        print(f"[INFO] Subject: {delivery['subject']}")
        print(
            "[INFO] Options: "
            f"verbose={delivery['verbose']}, "
            f"report_calls={delivery['report_calls']}"
        )
        print(
            "[INFO] Watchlist items included: "
            + ", ".join(delivery["watch_names"])
        )
        print("[INFO] Plain-text body preview:")
        print(delivery["report"])


# =========================
# EMAIL SENDER (GMAIL)
# =========================


def send_email_report(
    report: str,
    subject: str = "Weekly grocery specials report",
    html_report: Optional[str] = None,
    to_email: Optional[str] = None,
):
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

    recipient = str(to_email or cfg.get("to_email", gmail_user)).strip() or gmail_user
    smtp_host = str(cfg.get("smtp_host", "smtp.gmail.com")).strip()
    smtp_port = int(cfg.get("smtp_port", 587))
    smtp_use_tls = _coerce_bool(cfg.get("smtp_use_tls"), default=True)
    email_subject = resolve_email_subject(cfg, subject)

    msg = EmailMessage()
    msg["Subject"] = email_subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.set_content(report)
    if html_report:
        msg.add_alternative(html_report, subtype="html")

    context = ssl.create_default_context() if smtp_use_tls else None
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if smtp_use_tls:
            server.starttls(context=context)
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
    print(f"[INFO] Report emailed to {recipient}")


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


def build_email_test_html_report() -> str:
    """Return a small sample HTML table report for email testing."""
    return (
        '<html><body style="font-family: Arial, sans-serif; color: #222;">'
        "<h2>Email Test</h2>"
        "<p>This is a sample specials report used to verify email delivery.</p>"
        "<h2>Sample Item</h2>"
        '<table style="border-collapse: collapse; width: 100%;">'
        "<thead><tr>"
        '<th style="border: 1px solid #ccc; background: #f5f5f5; padding: 8px; '
        'text-align: left;">Store</th>'
        '<th style="border: 1px solid #ccc; background: #f5f5f5; padding: 8px; '
        'text-align: left;">Product</th>'
        '<th style="border: 1px solid #ccc; background: #f5f5f5; padding: 8px; '
        'text-align: left;">Brand</th>'
        '<th style="border: 1px solid #ccc; background: #f5f5f5; padding: 8px; '
        'text-align: left;">Price</th>'
        '<th style="border: 1px solid #ccc; background: #f5f5f5; padding: 8px; '
        'text-align: left;">Size</th>'
        '<th style="border: 1px solid #ccc; background: #f5f5f5; padding: 8px; '
        'text-align: left;">Link</th>'
        "</tr></thead><tbody>"
        "<tr>"
        '<td style="border: 1px solid #ccc; padding: 8px;">Coles</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">Example Product</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">Example Brand</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">$4.50</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">165g</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">'
        '<a href="https://example.com/coles">Open</a></td>'
        "</tr>"
        "<tr>"
        '<td style="border: 1px solid #ccc; padding: 8px;">Woolworths</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">Example Product</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">Example Brand</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">$4.80</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">180g</td>'
        '<td style="border: 1px solid #ccc; padding: 8px;">'
        '<a href="https://example.com/woolworths">Open</a></td>'
        "</tr>"
        "</tbody></table>"
        "<p>If you received this email, the email configuration is working.</p>"
        "</body></html>"
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


def main(
    send_email: bool = True,
    testing_mode: bool = False,
    watchlist_path: str = "watchlist.yaml",
):
    """Run the full flow: load watchlist, fetch offers, report, email."""
    RUN_API_CALL_COUNT["Coles"] = 0
    RUN_API_CALL_COUNT["Woolworths"] = 0
    watchlist = load_watchlist(watchlist_path)
    freshness_config = _load_specials_freshness_config()
    vendor_state = _load_vendor_specials_state()
    today = datetime.now(UTC).date()
    vendor_plans = _prepare_vendor_processing_plans(
        freshness_config,
        vendor_state,
        today,
    )
    active_stores = {
        vendor for vendor, plan in vendor_plans.items() if plan.should_query
    }
    all_offers: Dict[str, List[Offer]] = {}

    limit_error: Optional[str] = None
    try:
        offers_by_keyword = collect_offers_by_keyword(
            watchlist,
            allowed_stores=active_stores,
        )
        for watch_item in watchlist:
            all_offers[watch_item.name] = find_offers_for_watch_item(
                watch_item, offers_by_keyword
            )
    except APILimitExceeded as exc:
        limit_error = str(exc)
        _record_limit_warning(limit_error)
        print(f"[ERROR] {limit_error}")

    _, email_cfg = load_email_config()
    recipients = get_email_recipients(email_cfg)
    validate_watchlist_email_indices(watchlist, recipients)

    vendor_send_modes: Dict[str, str] = {}
    for vendor in STORE_NAMES:
        plan = vendor_plans[vendor]
        if not plan.should_query:
            continue

        vendor_watch_names = {
            watch_item.name for watch_item in watchlist if vendor in watch_item.stores
        }
        if not vendor_watch_names:
            continue
        vendor_offers = _build_vendor_offers_view(
            all_offers,
            vendor,
            allowed_watch_names=vendor_watch_names,
        )
        current_hash = _vendor_offer_signature(vendor_offers)
        state = vendor_state.setdefault(vendor, _default_vendor_state())
        state["last_checked_date"] = today.isoformat()

        reference_hash = state.get("reference_hash")
        has_changed = reference_hash is None or current_hash != reference_hash
        if has_changed:
            state["changed_this_cycle"] = True
            state["last_known_hash"] = current_hash
            vendor_send_modes[vendor] = "success"
            continue

        if today.weekday() == plan.schedule.force_send_day:
            vendor_send_modes[vendor] = "forced_send"

    deliveries: List[Dict[str, Any]] = []
    due_vendors = sorted(vendor_send_modes.keys())
    if due_vendors:
        due_vendor_set = set(due_vendors)
        combined_watchlist = [
            watch_item
            for watch_item in watchlist
            if due_vendor_set.intersection(set(watch_item.stores))
        ]
        combined_watch_names = {item.name for item in combined_watchlist}
        combined_offers: Dict[str, List[Offer]] = {}
        for watch_name, offers in all_offers.items():
            if watch_name not in combined_watch_names:
                continue
            combined_offers[watch_name] = [
                offer for offer in offers if offer.store in due_vendor_set
            ]

        subject, preamble = _build_run_subject_and_preamble(
            email_cfg,
            freshness_config,
            vendor_send_modes,
        )
        deliveries = build_email_deliveries(
            combined_watchlist,
            combined_offers,
            email_cfg,
            subject=subject,
        )
        for delivery in deliveries:
            delivery["report"] = _prepend_preamble(delivery["report"], preamble)
            delivery["html_report"] = _prepend_preamble_html(
                delivery["html_report"],
                preamble,
            )

        for vendor in due_vendors:
            vendor_state[vendor]["sent_this_cycle"] = True
            vendor_state[vendor]["last_sent_date"] = today.isoformat()

    _save_vendor_specials_state(vendor_state)

    if deliveries:
        print(deliveries[0]["report"])
    else:
        print("[INFO] No vendor reports due today based on freshness state.")

    if testing_mode:
        print("[INFO] Testing mode: email send skipped.")
        print_email_delivery_preview(deliveries)
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

    if send_email and not testing_mode and deliveries:
        for delivery in deliveries:
            send_email_report(
                delivery["report"],
                subject=delivery["subject"],
                html_report=delivery["html_report"],
                to_email=delivery["recipient"],
            )


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
        help=(
            "Run the checker in testing mode "
            "(prints results and per-recipient email previews, no email)"
        ),
    )
    parser.add_argument(
        "--test-email",
        action="store_true",
        help="Send a sample email report without calling the product APIs.",
    )
    parser.add_argument(
        "--watchlist",
        default="watchlist.yaml",
        help="Path to the watchlist YAML file (default: watchlist.yaml).",
    )

    args = parser.parse_args()

    if args.test_email:
        _, email_cfg = load_email_config()
        recipients = get_email_recipients(email_cfg)
        for recipient_index, recipient in enumerate(recipients or [None]):
            api_calls_footer = (
                build_api_calls_footer()
                if get_email_bool_option(
                    email_cfg,
                    "report_calls",
                    recipient_index,
                    default=False,
                )
                else None
            )
            send_email_report(
                append_api_calls_footer(
                    build_email_test_report(),
                    api_calls_footer,
                ),
                subject=str(
                    email_cfg.get(
                        "email_test_subject",
                        "Email test - grocery specials checker",
                    )
                ),
                html_report=append_api_calls_footer_html(
                    build_email_test_html_report(),
                    api_calls_footer,
                ),
                to_email=recipient,
            )
    elif args.test_coles:
        run_test_coles(args.test_coles)
    elif args.test_woolies:
        run_test_woolies(args.test_woolies)
    else:
        suppress_email = args.no_email or args.testing
        main(
            send_email=not suppress_email,
            testing_mode=args.testing,
            watchlist_path=args.watchlist,
        )
