"""Regression tests for vendor freshness comparisons."""

import os
import unittest
from datetime import date
from importlib import import_module
from unittest.mock import patch

os.environ.setdefault("RAPIDAPI_KEY", "test-key")

specials_checker = import_module("src.specials_checker")
Offer = specials_checker.Offer
_default_vendor_state = specials_checker._default_vendor_state
APILimitExceeded = specials_checker.APILimitExceeded
FAILED_VENDOR_QUERIES = specials_checker.FAILED_VENDOR_QUERIES
WatchItem = specials_checker.WatchItem
collect_offers_by_keyword = specials_checker.collect_offers_by_keyword
normalise_coles_product = specials_checker.normalise_coles_product
_prepare_vendor_processing_plans = specials_checker._prepare_vendor_processing_plans
_snapshot_vendor_offers = specials_checker._snapshot_vendor_offers
_validate_product_page = specials_checker._validate_product_page
_vendor_offer_price_signature = specials_checker._vendor_offer_price_signature


def _offer(product_title: str, price: float, barcode: str) -> Offer:
    return Offer(
        watch_name="Chocolate",
        store="Coles",
        product_title=product_title,
        brand="Example",
        price=price,
        size="200 g",
        url=f"https://example.test/{barcode}",
        barcode=barcode,
    )


class VendorFreshnessTests(unittest.TestCase):
    def test_new_product_does_not_make_unchanged_prices_fresh(self) -> None:
        reference = {
            "Chocolate": [
                _offer("Existing block", 3.50, "existing"),
            ]
        }
        current = {
            "Chocolate": [
                _offer("Existing block", 3.50, "existing"),
                _offer("New block", 4.00, "new"),
            ]
        }

        self.assertEqual(
            _vendor_offer_price_signature(reference, reference),
            _vendor_offer_price_signature(current, reference),
        )

    def test_price_change_for_previous_product_is_detected(self) -> None:
        reference = {
            "Chocolate": [
                _offer("Existing block", 3.50, "existing"),
            ]
        }
        current = {
            "Chocolate": [
                _offer("Existing block", 4.00, "existing"),
            ]
        }

        self.assertNotEqual(
            _vendor_offer_price_signature(reference, reference),
            _vendor_offer_price_signature(current, reference),
        )

    def test_barcode_appearance_falls_back_to_product_details(self) -> None:
        reference = {"Chocolate": [_offer("Existing block", 3.50, "")]}
        current = {"Chocolate": [_offer("Existing block", 3.50, "new-barcode")]}

        self.assertEqual(
            _vendor_offer_price_signature(reference, reference),
            _vendor_offer_price_signature(current, reference),
        )

    def test_unmatched_product_with_same_details_is_ignored(self) -> None:
        reference = {"Chocolate": [_offer("Existing block", 3.50, "")]}
        current = {
            "Chocolate": [
                _offer("Existing block", 4.00, "new-barcode"),
                _offer("Existing block", 3.50, ""),
            ]
        }

        self.assertEqual(
            _vendor_offer_price_signature(reference, reference),
            _vendor_offer_price_signature(current, reference),
        )

    def test_conflicting_barcode_is_not_details_matched(self) -> None:
        reference = {"Chocolate": [_offer("Existing block", 3.50, "old-barcode")]}
        current = {"Chocolate": [_offer("Existing block", 3.50, "new-barcode")]}

        self.assertNotEqual(
            _vendor_offer_price_signature(reference, reference),
            _vendor_offer_price_signature(current, reference),
        )

    def test_coles_barcode_is_preserved(self) -> None:
        offer = normalise_coles_product(
            "Chocolate",
            {"name": "Existing block", "price": 3.50, "gtin": "123"},
        )

        self.assertEqual(offer.barcode, "123")

    def test_incomplete_api_page_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _validate_product_page({"totalResults": 5}, [])

        with self.assertRaises(ValueError):
            _validate_product_page({"totalPages": 2, "results": []}, [])

        with self.assertRaises(ValueError):
            _validate_product_page({"currentPage": 2, "results": []}, [])

    def test_api_limit_does_not_abort_other_vendor_queries(self) -> None:
        watchlist = [
            WatchItem(
                name="Chocolate",
                match_keywords=["chocolate"],
                include_keywords=["chocolate"],
                exclude_keywords=[],
                stores=["Coles", "Woolworths"],
            )
        ]
        FAILED_VENDOR_QUERIES.clear()
        with (
            patch.object(
                specials_checker,
                "search_coles",
                side_effect=APILimitExceeded("Coles limit"),
            ),
            patch.object(
                specials_checker,
                "search_woolies",
                return_value={
                    "results": [
                        {"name": "Chocolate bar", "price": 3.50, "barcode": "123"}
                    ]
                },
            ),
        ):
            offers = collect_offers_by_keyword(watchlist)

        self.assertIn("Coles", FAILED_VENDOR_QUERIES)
        self.assertEqual(offers["chocolate"][0].store, "Woolworths")

    def test_retries_keep_the_cycle_start_reference(self) -> None:
        reference = {"Chocolate": [_offer("Existing block", 3.50, "existing")]}
        state = {
            "Coles": _default_vendor_state(),
            "Woolworths": _default_vendor_state(),
        }
        state["Coles"]["last_known_payload"] = _snapshot_vendor_offers(reference)
        state["Coles"]["last_known_hash"] = "prior-cycle-hash"

        _prepare_vendor_processing_plans({}, state, date(2026, 8, 5))

        state["Coles"]["last_known_payload"] = {
            "Chocolate": [_offer("Existing block", 4.00, "existing")]
        }
        self.assertEqual(
            state["Coles"]["reference_payload"],
            _snapshot_vendor_offers(reference),
        )


if __name__ == "__main__":
    unittest.main()
