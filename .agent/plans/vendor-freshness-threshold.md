# Vendor freshness threshold

## Goal

Detect a new weekly offer set once per vendor when the vendor's catalogue has
materially changed, while ignoring one-off added or removed offers that can be
caused by API search variation. Preserve explicit empty watchlist lists during
the Excel round trip, then remove the completed improvement-list entries.

## Scope

Included: per-vendor matching/churn detection, configurable threshold,
regression tests, Excel `email_indices: []` preservation, user-facing docs, and
the resolved improvement-list cleanup. Excluded: API/query changes, state-file
migration, email delivery changes, and changing the existing schedule.

## Repository evidence

- `src/specials_checker.py` now evaluates freshness once per vendor from a
  deduplicated physical catalogue: a safely matched price change is immediate,
  otherwise distinct additions and removals are thresholded.
- `tests/test_freshness.py` covers price changes, below/at-threshold churn,
  overlapping watch-item deduplication, and barcode-less aliases.
- `config/specials_freshness.yaml.example` and README document the freshness
  settings and comparison semantics.
- `src/export_watchlist_to_excel.py` / `src/import_watchlist_from_excel.py`
  preserve explicit `[]`, including `email_indices`.

## Constraints and invariants

- Freshness and send mode remain one decision per vendor, not per watch item.
- Any price change among safely matched products remains fresh immediately.
- Barcode-first matching semantics remain intact; a conflicting barcode cannot
  silently become a details match.
- Catalogue churn is deduplicated across overlapping watch items before it is
  counted, so one product cannot reach the threshold twice.
- A barcode-less alias is merged with a matching barcoded offer only when its
  details identify one barcode; ambiguous barcode conflicts remain distinct.
- A first usable vendor snapshot still bootstraps as fresh; failed API results
  and retry reference stability keep their existing behavior.
- Preserve user-owned `config/vendor_specials_state.json`.

## Proposed approach

Flatten each vendor's offers into a deduplicated physical catalogue. Merge a
barcode-less alias with a barcoded offer only when its details unambiguously
identify one barcode. Match the reference and current catalogues with the
existing barcode-first rules. A matched price change is fresh. Otherwise count
unmatched additions plus unmatched removals. Default `minimum_offer_changes: 3`
filters a single appearance/disappearance (one event) and a single replacement
(two events), while detecting a materially rotated offer set. Make the value
configurable per vendor through the existing freshness configuration. Keep the
full snapshot hash for persistence/reporting; it is not the freshness decision.

## Implementation steps

1. [x] Add validated minimum-churn configuration and a matching/change summary
   in `src/specials_checker.py`.
2. [x] Use the summary for the one-per-vendor freshness decision and log the
   evidence that caused it.
3. [x] Extend `tests/test_freshness.py` for below/at-threshold churn, price
   changes, safely deduplicated aliases, and explicit-empty Excel round trips.
4. [x] Document the threshold and matching rules in the README and config
   example.
5. [x] Remove resolved items 2 and 3 from `improvements.md`.

## Validation plan

Run `python -m unittest tests.test_freshness -v`, `python -m ruff check src
tests`, `python -m black --check src tests`, and `python -m compileall
src/import_watchlist_from_excel.py src/export_watchlist_to_excel.py
src/specials_checker.py`.

## Risks and rollback

A too-low threshold could treat API noise as fresh; a too-high value could delay
real catalogue rotations until the fallback day. The default and per-vendor
override are documented and regression-tested. Revert this focused change to
restore the prior matched-price-only behavior; persisted state remains
compatible because its shape is unchanged.

## Progress log

- [x] 2026-09-02: Read-only exploration identified matched-price-only comparison
  as the cause and found a missing `email_indices: []` round trip.
- [x] 2026-09-02: Implemented the vendor-wide threshold comparison and safe
  barcode-less alias deduplication; added the focused regression coverage.
- [x] 2026-09-02: `python -m unittest tests.test_freshness -v` passed (18
  tests) and `python -m black --check src\\specials_checker.py
  tests\\test_freshness.py` passed.
- [x] 2026-09-02: Updated user-facing documentation and removed the resolved
  improvement ideas.
- [x] 2026-09-02: Independent validation and review completed: the focused
  `unittest` suite passed (18 tests), Black, `compileall`, and `git diff --check`
  passed, and the reviewer found no material issues. Ruff still reports 19
  pre-existing, untouched Excel-helper findings.

## Outcome

Complete. A vendor is fresh once per cycle when a safely matched product's
price changes, or when its deduplicated catalogue reaches the configured
addition/removal threshold (default `3`). Overlapping results and unambiguous
barcode-less aliases do not inflate that count; barcode conflicts remain
protected. Explicit `email_indices: []` now survives Excel export and import,
and the two resolved improvement ideas have been removed.

Independent validation passed: the focused `unittest` suite passed (18 tests),
Black, `compileall`, and `git diff --check` passed, and final review found no
material issues. Ruff continues to report 19 pre-existing, untouched findings
in the Excel helpers.
