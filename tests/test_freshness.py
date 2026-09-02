"""Regression tests for vendor freshness comparisons."""

import os
import unittest
from datetime import date
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from src.export_watchlist_to_excel import export_watchlist_to_excel
from src.import_watchlist_from_excel import import_watchlist_from_excel

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
_resolve_vendor_schedule = specials_checker._resolve_vendor_schedule
_snapshot_vendor_offers = specials_checker._snapshot_vendor_offers
_summarise_vendor_freshness = specials_checker._summarise_vendor_freshness
_decide_vendor_freshness = specials_checker._decide_vendor_freshness
_validate_product_page = specials_checker._validate_product_page


def _offer(
    product_title: str,
    price: float,
    barcode: str,
    watch_name: str = "Chocolate",
) -> Offer:
    return Offer(
        watch_name=watch_name,
        store="Coles",
        product_title=product_title,
        brand="Example",
        price=price,
        size="200 g",
        url=f"https://example.test/{barcode}",
        barcode=barcode,
    )


class VendorFreshnessTests(unittest.TestCase):
    def test_addition_below_default_threshold_remains_stale(self) -> None:
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

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(comparison.added_offer_count, 1)
        self.assertEqual(
            _decide_vendor_freshness("reference", comparison, 3),
            (False, "below_catalogue_churn_threshold"),
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

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(comparison.price_change_count, 1)
        self.assertEqual(
            _decide_vendor_freshness("reference", comparison, 99),
            (True, "price_change"),
        )

    def test_removal_below_default_threshold_remains_stale(
        self,
    ) -> None:
        reference = {
            "Chocolate": [
                _offer("Existing block", 3.50, "existing"),
                _offer("Absent block", 4.00, "absent"),
            ]
        }
        current = {"Chocolate": [_offer("Existing block", 3.50, "existing")]}

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(comparison.removed_offer_count, 1)
        self.assertEqual(
            _decide_vendor_freshness("reference", comparison, 3),
            (False, "below_catalogue_churn_threshold"),
        )

    def test_removals_at_default_threshold_make_vendor_fresh(
        self,
    ) -> None:
        reference = {
            "Chocolate": [
                _offer("Existing block", 3.50, "existing"),
                _offer("Absent block one", 4.00, "absent-one"),
                _offer("Absent block two", 4.00, "absent-two"),
                _offer("Absent block three", 4.00, "absent-three"),
            ]
        }
        current = {"Chocolate": [_offer("Existing block", 3.50, "existing")]}

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(comparison.removed_offer_count, 3)
        self.assertEqual(
            _decide_vendor_freshness("reference", comparison, 3),
            (True, "catalogue_churn"),
        )

    def test_barcode_appearance_still_matches_by_details(self) -> None:
        reference = {"Chocolate": [_offer("Existing block", 3.50, "")]}
        current = {"Chocolate": [_offer("Existing block", 4.00, "new-barcode")]}

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(
            (comparison.matched_offer_count, comparison.price_change_count),
            (1, 1),
        )

    def test_single_replacement_is_below_default_threshold(self) -> None:
        reference = {"Chocolate": [_offer("Existing block", 3.50, "old-barcode")]}
        current = {"Chocolate": [_offer("Existing block", 3.50, "new-barcode")]}

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(
            (
                comparison.price_change_count,
                comparison.added_offer_count,
                comparison.removed_offer_count,
            ),
            (0, 1, 1),
        )
        self.assertEqual(
            _decide_vendor_freshness("reference", comparison, 3),
            (False, "below_catalogue_churn_threshold"),
        )

    def test_conflicting_barcodes_are_not_details_matched(self) -> None:
        reference = {"Chocolate": [_offer("Existing block", 3.50, "old-barcode")]}
        current = {"Chocolate": [_offer("Existing block", 4.00, "new-barcode")]}

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(
            (comparison.matched_offer_count, comparison.price_change_count),
            (0, 0),
        )
        self.assertEqual(
            (comparison.added_offer_count, comparison.removed_offer_count),
            (1, 1),
        )

    def test_additions_at_default_threshold_make_vendor_fresh(self) -> None:
        reference = {"Chocolate": [_offer("Existing block", 3.50, "existing")]}
        current = {
            "Chocolate": [
                _offer("Existing block", 3.50, "existing"),
                _offer("New block one", 4.00, "new-one"),
                _offer("New block two", 4.00, "new-two"),
                _offer("New block three", 4.00, "new-three"),
            ]
        }

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(comparison.added_offer_count, 3)
        self.assertEqual(
            _decide_vendor_freshness("reference", comparison, 3),
            (True, "catalogue_churn"),
        )

    def test_replacement_at_default_threshold_makes_vendor_fresh(self) -> None:
        reference = {
            "Chocolate": [
                _offer("Existing block", 3.50, "existing"),
                _offer("Removed block one", 4.00, "removed-one"),
                _offer("Removed block two", 4.00, "removed-two"),
            ]
        }
        current = {
            "Chocolate": [
                _offer("Existing block", 3.50, "existing"),
                _offer("Added replacement", 4.00, "added"),
            ]
        }

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(
            (comparison.added_offer_count, comparison.removed_offer_count),
            (1, 2),
        )
        self.assertEqual(
            _decide_vendor_freshness("reference", comparison, 3),
            (True, "catalogue_churn"),
        )

    def test_overlapping_watch_items_do_not_count_one_offer_twice(self) -> None:
        reference = {
            "Chocolate": [_offer("Existing block", 3.50, "existing", "Chocolate")],
            "Snacks": [_offer("Existing block", 3.50, "existing", "Snacks")],
        }
        current = {
            "Chocolate": [
                _offer("Existing block", 3.50, "existing", "Chocolate"),
                _offer("New block", 4.00, "new", "Chocolate"),
            ],
            "Snacks": [
                _offer("Existing block", 3.50, "existing", "Snacks"),
                _offer("New block", 4.00, "new", "Snacks"),
            ],
        }

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(
            (comparison.matched_offer_count, comparison.added_offer_count),
            (1, 1),
        )

    def test_barcodeless_overlap_aliases_do_not_count_as_additions(self) -> None:
        reference = {
            "Exact search": [
                _offer("Block one", 3.50, "one", "Exact search"),
                _offer("Block two", 3.50, "two", "Exact search"),
                _offer("Block three", 3.50, "three", "Exact search"),
            ]
        }
        current = {
            "Exact search": [
                _offer("Block one", 3.50, "one", "Exact search"),
                _offer("Block two", 3.50, "two", "Exact search"),
                _offer("Block three", 3.50, "three", "Exact search"),
            ],
            "Broad search": [
                _offer("Block one", 3.50, "", "Broad search"),
                _offer("Block two", 3.50, "", "Broad search"),
                _offer("Block three", 3.50, "", "Broad search"),
            ],
        }

        comparison = _summarise_vendor_freshness(reference, current)

        self.assertEqual(
            (
                comparison.matched_offer_count,
                comparison.added_offer_count,
                comparison.removed_offer_count,
            ),
            (3, 0, 0),
        )
        self.assertEqual(
            _decide_vendor_freshness("reference", comparison, 3),
            (False, "below_catalogue_churn_threshold"),
        )

    def test_first_snapshot_bootstraps_as_fresh(self) -> None:
        comparison = _summarise_vendor_freshness({}, {"Chocolate": []})

        self.assertEqual(
            _decide_vendor_freshness(None, comparison, 3),
            (True, "bootstrap"),
        )

    def test_vendor_churn_threshold_uses_default_and_override(self) -> None:
        config = {
            "vendors": {
                "default": {"minimum_offer_changes": 3},
                "Coles": {"minimum_offer_changes": 5},
            }
        }

        self.assertEqual(
            _resolve_vendor_schedule(config, "Coles").minimum_offer_changes,
            5,
        )
        self.assertEqual(
            _resolve_vendor_schedule(config, "Woolworths").minimum_offer_changes,
            3,
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


class ExcelWatchlistRoundTripTests(unittest.TestCase):
    def test_explicit_empty_email_indices_round_trip(self) -> None:
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            source_path = directory_path / "watchlist.yaml"
            excel_path = directory_path / "watchlist.xlsx"
            imported_path = directory_path / "imported_watchlist.yaml"
            source_path.write_text(
                yaml.safe_dump(
                    {
                        "items": [
                            {
                                "name": "Chocolate",
                                "match_keywords": ["chocolate"],
                                "email_indices": [],
                            }
                        ]
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            export_watchlist_to_excel(str(source_path), str(excel_path))
            import_watchlist_from_excel(str(excel_path), str(imported_path))

            imported = yaml.safe_load(imported_path.read_text(encoding="utf-8"))

        self.assertEqual(imported["items"][0]["email_indices"], [])


if __name__ == "__main__":
    unittest.main()
