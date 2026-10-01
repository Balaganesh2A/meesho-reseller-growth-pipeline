"""Given-When-Then tests for part2_engine/growth_engine.py (run with pytest)."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from growth_engine import compute_mom_table, is_flagged, mom_growth, validate_feed  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")
VALID_FEED = os.path.join(FIXTURES, "monthly_category_revenue.csv")
CORRUPTED_FEED = os.path.join(FIXTURES, "corrupted_feed.csv")


def test_april_to_may_ethnic_wear_is_flagged():
    # GIVEN April->May Ethnic Wear revenue moves from 104520.77 to 185107.61
    previous, current = 104520.77, 185107.61
    # WHEN mom_growth then is_flagged run on it
    pct = mom_growth(previous, current)
    result = is_flagged(pct)
    # THEN mom_growth returns 77.1 and is_flagged returns "flagged"
    assert pct == 77.1
    assert result == "flagged"


def test_may_to_june_beauty_is_not_flagged():
    # GIVEN May->June Beauty & Personal Care revenue moves from 35542.11 to 37559.07
    previous, current = 35542.11, 37559.07
    # WHEN evaluated
    pct = mom_growth(previous, current)
    result = is_flagged(pct)
    # THEN mom_growth returns 5.67 and is_flagged returns "not_flagged"
    assert pct == 5.67
    assert result == "not_flagged"


def test_exact_boundary_is_escalated():
    # GIVEN a synthetic pair chosen to land exactly on the 8% threshold
    previous, current = 100000, 108000
    # WHEN evaluated
    pct = mom_growth(previous, current)
    result = is_flagged(pct)
    # THEN mom_growth returns exactly 8.0 and the case is escalated,
    #      neither "flagged" nor "not_flagged"
    assert pct == 8.0
    assert result == "escalate_exact_boundary"
    assert result not in ("flagged", "not_flagged")


def test_corrupted_feed_fails_with_three_ordered_errors():
    # GIVEN the corrupted feed fixture
    # WHEN validate_feed runs on it
    valid, errors = validate_feed(CORRUPTED_FEED)
    # THEN it returns (False, errors) with exactly 3 errors, in row order:
    #      negative revenue, missing category, missing revenue
    assert valid is False
    assert errors == [
        "line 3: negative revenue (-4200.0) for category=Western Wear",
        "line 4: missing category (month=July)",
        "line 6: missing revenue (category=Home & Kitchen)",
    ]


def test_valid_feed_passes():
    # GIVEN the verified Part 1 monthly_category_revenue fixture (15 rows)
    # WHEN validate_feed runs on it
    result = validate_feed(VALID_FEED)
    # THEN it returns (True, [])
    assert result == (True, [])


def test_full_mom_tables_from_valid_feed():
    # GIVEN the verified Part 1 feed
    # WHEN the MoM table is computed for consecutive month pairs
    rows = compute_mom_table(VALID_FEED)
    got = [(r["previous_month"], r["month"], r["category"], r["mom_pct"], r["result"]) for r in rows]
    # THEN May-vs-April has all 5 flagged and June-vs-May has 4 of 5 flagged
    assert got == [
        ("April", "May", "Ethnic Wear", 77.1, "flagged"),
        ("April", "May", "Western Wear", -23.6, "flagged"),
        ("April", "May", "Kids Wear", -23.48, "flagged"),
        ("April", "May", "Home & Kitchen", -9.25, "flagged"),
        ("April", "May", "Beauty & Personal Care", -12.75, "flagged"),
        ("May", "June", "Ethnic Wear", -58.74, "flagged"),
        ("May", "June", "Western Wear", 11.97, "flagged"),
        ("May", "June", "Kids Wear", 23.9, "flagged"),
        ("May", "June", "Home & Kitchen", 42.59, "flagged"),
        ("May", "June", "Beauty & Personal Care", 5.67, "not_flagged"),
    ]
