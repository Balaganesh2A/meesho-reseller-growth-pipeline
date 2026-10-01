"""Given-When-Then tests for part4_agent/mock_agent_runner.py (run with: python -m pytest part4_agent)."""

import csv
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, PROJECT_ROOT)

import mock_agent_runner as runner  # noqa: E402
from part2_engine import growth_engine  # noqa: E402
from part3_narrative import narrative_generator  # noqa: E402

FEED = os.path.join(PROJECT_ROOT, "part1_sql", "output", "monthly_category_revenue.csv")
CORRUPTED = os.path.join(PROJECT_ROOT, "part2_engine", "fixtures", "corrupted_feed.csv")
PART2_OUTPUT = os.path.join(PROJECT_ROOT, "part2_engine", "output", "mom_growth_results.csv")

SEVEN_KEYS = ["run_month", "validation_status", "validation_errors", "flagged_categories",
              "suppressed_categories", "escalated_categories", "action_taken"]
ENTRY_KEYS = {"category", "mom_pct", "previous_revenue", "current_revenue", "drafted", "message"}


def _csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _part2(month):
    """Verified Part 2 rows for the comparison ending in `month`."""
    return [r for r in _csv(PART2_OUTPUT) if r["month"] == month]


def _feed_value(month, category):
    return next(r["revenue"] for r in _csv(FEED) if (r["month"], r["category"]) == (month, category))


def _write_feed(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "category", "revenue", "n_orders"])
        w.writerows(rows)
    return str(path)


def _expected_ranking(month):
    flagged = [r for r in _part2(month) if r["result"] == "flagged"]
    return sorted(flagged, key=lambda r: -abs(float(r["mom_pct"])))


# ---------------- schema ----------------

@pytest.mark.parametrize("args", [
    ("May", FEED, FEED),
    ("June", FEED, FEED),
    ("July", FEED, CORRUPTED),
])
def test_exactly_seven_keys_and_json_serialisable(args):
    # GIVEN any scenario (success or hard stop)
    # WHEN the runner executes
    out = runner.run(*args)
    # THEN the result has exactly the seven section-4.3 keys, in order, and is valid JSON
    assert list(out) == SEVEN_KEYS
    assert json.loads(json.dumps(out)) == out
    assert out["validation_status"] in ("valid", "invalid")
    assert out["action_taken"] in ("drafted_and_held_for_approval", "hard_stop")
    for entry in out["flagged_categories"]:
        assert set(entry) == ENTRY_KEYS and entry["drafted"] is True


# ---------------- May scenario ----------------

def test_may_scenario():
    # GIVEN the verified Part 1 feed (April and May)
    # WHEN the runner executes for May
    out = runner.run("May", FEED, FEED)
    drafted = [(e["category"], e["mom_pct"]) for e in out["flagged_categories"]]
    # THEN it matches the brief's acceptance values exactly ...
    assert out["run_month"] == "May"
    assert out["validation_status"] == "valid" and out["validation_errors"] == []
    assert drafted == [("Ethnic Wear", 77.1), ("Western Wear", -23.6), ("Kids Wear", -23.48)]
    assert sorted(out["suppressed_categories"]) == ["Beauty & Personal Care", "Home & Kitchen"]
    assert out["escalated_categories"] == []
    assert out["action_taken"] == "drafted_and_held_for_approval"
    # ... and the verified Part 2 output, ranked by abs(mom_pct)
    ranking = _expected_ranking("May")
    assert drafted == [(r["category"], float(r["mom_pct"])) for r in ranking[:3]]
    assert out["suppressed_categories"] == [r["category"] for r in ranking[3:]]


# ---------------- June scenario ----------------

def test_june_scenario():
    # GIVEN the verified Part 1 feed (May and June)
    # WHEN the runner executes for June
    out = runner.run("June", FEED, FEED)
    drafted = [(e["category"], e["mom_pct"]) for e in out["flagged_categories"]]
    # THEN it matches the brief's acceptance values exactly ...
    assert out["validation_status"] == "valid"
    assert drafted == [("Ethnic Wear", -58.74), ("Home & Kitchen", 42.59), ("Kids Wear", 23.9)]
    assert out["suppressed_categories"] == ["Western Wear"]
    assert out["escalated_categories"] == []
    # ... Beauty & Personal Care (not flagged) appears in neither list ...
    assert "Beauty & Personal Care" not in [e["category"] for e in out["flagged_categories"]]
    assert "Beauty & Personal Care" not in out["suppressed_categories"]
    # ... and it agrees with the verified Part 2 output
    ranking = _expected_ranking("June")
    assert drafted == [(r["category"], float(r["mom_pct"])) for r in ranking[:3]]
    assert out["suppressed_categories"] == [r["category"] for r in ranking[3:]]
    not_flagged = [r["category"] for r in _part2("June") if r["result"] == "not_flagged"]
    assert not_flagged == ["Beauty & Personal Care"]


# ---------------- corrupted feed / hard stop ----------------

def test_corrupted_feed_hard_stops(monkeypatch):
    # GIVEN the corrupted fixture as the current-month feed, and spies on MoM and drafting
    calls = {"mom": 0, "narrative": 0}
    monkeypatch.setattr(runner, "mom_growth", lambda *a: calls.__setitem__("mom", calls["mom"] + 1))
    monkeypatch.setattr(runner, "generate_narrative", lambda *a: calls.__setitem__("narrative", calls["narrative"] + 1))
    # WHEN the runner executes
    out = runner.run("July", FEED, CORRUPTED)
    # THEN it hard-stops with exactly Part 2's three error strings, in order,
    #      no MoM is computed, no narrative is drafted, and all lists are empty
    assert out["validation_status"] == "invalid"
    assert out["action_taken"] == "hard_stop"
    assert out["validation_errors"] == [
        "line 3: negative revenue (-4200.0) for category=Western Wear",
        "line 4: missing category (month=July)",
        "line 6: missing revenue (category=Home & Kitchen)",
    ]
    assert out["validation_errors"] == growth_engine.validate_feed(CORRUPTED)[1]
    assert out["flagged_categories"] == [] and out["suppressed_categories"] == []
    assert out["escalated_categories"] == []
    assert calls == {"mom": 0, "narrative": 0}


@pytest.mark.parametrize("month,prev_rows,cur_rows,needle", [
    ("Smarch", [], [], "unknown or unsupported run month"),
    ("May", [["March", "A", "100.00", "1"]], [["May", "A", "200.00", "1"]], "no April rows"),
    ("May", [["April", "A", "100.00", "1"]], [["June", "A", "200.00", "1"]], "no May rows"),
    ("May", [["April", "A", "100.00", "1"]], [["May", "A", "200.00", "1"], ["May", "B", "50.00", "1"]],
     "no April revenue for category=B"),
    ("May", [["April", "A", "0", "1"]], [["May", "A", "200.00", "1"]], "MoM undefined"),
])
def test_insufficient_data_hard_stops(tmp_path, month, prev_rows, cur_rows, needle):
    # GIVEN feeds that cannot support the requested comparison
    prev = _write_feed(tmp_path / "prev.csv", prev_rows)
    cur = _write_feed(tmp_path / "cur.csv", cur_rows)
    # WHEN the runner executes
    out = runner.run(month, prev, cur)
    # THEN it hard-stops with a clear error and no partial output
    assert out["action_taken"] == "hard_stop" and out["validation_status"] == "invalid"
    assert any(needle in e for e in out["validation_errors"])
    assert out["flagged_categories"] == [] and out["suppressed_categories"] == []


# ---------------- top-3 cap and suppression ----------------

def test_top3_cap_and_suppression_with_many_flagged(tmp_path):
    # GIVEN six categories that all move well beyond 8%
    prev = _write_feed(tmp_path / "prev.csv", [["April", c, "100.00", "1"] for c in "ABCDEF"])
    cur = _write_feed(tmp_path / "cur.csv", [["May", c, v, "1"] for c, v in
                                             zip("ABCDEF", ["150.00", "40.00", "180.00", "120.00", "75.00", "160.00"])])
    # WHEN the runner executes
    out = runner.run("May", prev, cur)
    # THEN exactly 3 are drafted (largest |MoM| first) and the other 3 are suppressed in rank order
    assert [e["category"] for e in out["flagged_categories"]] == ["C", "B", "F"]   # 80, -60, 60
    assert out["suppressed_categories"] == ["A", "E", "D"]                         # 50, -25, 20 by magnitude
    assert len(out["flagged_categories"]) == runner.DRAFT_CAP == 3


def test_top3_suppressed_order_is_by_magnitude(tmp_path):
    # GIVEN suppressed categories with mixed signs
    prev = _write_feed(tmp_path / "prev.csv", [["April", c, "100.00", "1"] for c in "ABCDE"])
    cur = _write_feed(tmp_path / "cur.csv", [["May", c, v, "1"] for c, v in
                                             zip("ABCDE", ["200.00", "190.00", "180.00", "120.00", "70.00"])])
    # WHEN the runner executes
    out = runner.run("May", prev, cur)
    # THEN the suppressed list follows abs(mom_pct) descending: E (-30) before D (+20)
    assert out["suppressed_categories"] == ["E", "D"]


def test_fewer_than_three_flagged_suppresses_nothing(tmp_path):
    # GIVEN only one category beyond the threshold
    prev = _write_feed(tmp_path / "prev.csv", [["April", "A", "100.00", "1"], ["April", "B", "100.00", "1"]])
    cur = _write_feed(tmp_path / "cur.csv", [["May", "A", "150.00", "1"], ["May", "B", "103.00", "1"]])
    # WHEN the runner executes
    out = runner.run("May", prev, cur)
    # THEN one draft, nothing suppressed, and the not_flagged category is in no list
    assert [e["category"] for e in out["flagged_categories"]] == ["A"]
    assert out["suppressed_categories"] == [] and out["escalated_categories"] == []


def test_zero_flagged_is_a_valid_success(tmp_path):
    # GIVEN no category crossing the threshold
    prev = _write_feed(tmp_path / "prev.csv", [["April", "A", "100.00", "1"]])
    cur = _write_feed(tmp_path / "cur.csv", [["May", "A", "105.00", "1"]])
    # WHEN the runner executes
    out = runner.run("May", prev, cur)
    # THEN zero drafts is a correct success, still held for approval
    assert out["validation_status"] == "valid"
    assert out["flagged_categories"] == [] and out["suppressed_categories"] == []
    assert out["action_taken"] == "drafted_and_held_for_approval"


def test_exact_boundary_is_escalated_not_drafted(tmp_path):
    # GIVEN the synthetic 8.0% boundary pair alongside a flagged category
    prev = _write_feed(tmp_path / "prev.csv", [["April", "Boundary", "100000", "1"], ["April", "Mover", "100.00", "1"]])
    cur = _write_feed(tmp_path / "cur.csv", [["May", "Boundary", "108000", "1"], ["May", "Mover", "150.00", "1"]])
    # WHEN the runner executes
    out = runner.run("May", prev, cur)
    # THEN the boundary category is escalated only - never flagged, suppressed or dropped
    assert out["escalated_categories"] == ["Boundary"]
    assert [e["category"] for e in out["flagged_categories"]] == ["Mover"]
    assert "Boundary" not in out["suppressed_categories"]


# ---------------- numerical traceability ----------------

@pytest.mark.parametrize("month,prev_month", [("May", "April"), ("June", "May")])
def test_every_number_traces_to_source(month, prev_month):
    # GIVEN a successful real-data run
    out = runner.run(month, FEED, FEED)
    part2 = {r["category"]: r for r in _part2(month)}
    for e in out["flagged_categories"]:
        p2 = part2[e["category"]]
        # WHEN an entry is inspected
        # THEN its revenues equal the Part 1 feed, its mom_pct equals the Part 2 output,
        #      and every number in its message is one of those values or the 8% threshold
        assert e["previous_revenue"] == float(_feed_value(prev_month, e["category"]))
        assert e["current_revenue"] == float(_feed_value(month, e["category"]))
        assert e["mom_pct"] == float(p2["mom_pct"])
        allowed = {p2["previous_revenue"], p2["current_revenue"], p2["mom_pct"], "8"}
        assert set(re.findall(r"-?\d+(?:\.\d+)?", e["message"])) <= allowed
        assert e["category"] in e["message"] and f"{p2['mom_pct']}%" in e["message"]


# ---------------- Part 2 / Part 3 integration ----------------

def test_runner_uses_part2_and_part3_functions_unmodified():
    # GIVEN the runner module
    # WHEN its tool references are inspected
    # THEN they are the Part 2 and Part 3 functions themselves, not re-implementations
    assert runner.validate_feed is growth_engine.validate_feed
    assert runner.mom_growth is growth_engine.mom_growth
    assert runner.is_flagged is growth_engine.is_flagged
    assert runner.generate_narrative is narrative_generator.generate_narrative


def test_generate_narrative_called_with_verified_rows(monkeypatch):
    # GIVEN a spy wrapped around Part 3's real generate_narrative
    calls = []
    real = narrative_generator.generate_narrative
    monkeypatch.setattr(runner, "generate_narrative", lambda row: calls.append(dict(row)) or real(row))
    # WHEN the May scenario runs
    out = runner.run("May", FEED, FEED)
    # THEN it is called once per drafted category (3, not 5) with the verified Part 2 rows,
    #      and each message is exactly its output
    part2 = {r["category"]: r for r in _part2("May")}
    assert calls == [part2[e["category"]] for e in out["flagged_categories"]]
    assert len(calls) == 3
    for e, row in zip(out["flagged_categories"], calls):
        assert e["message"] == real(row)


# ---------------- output guardrail ----------------

@pytest.mark.parametrize("suffix,needle", [
    (" Revenue may reach INR 999999.99 next month.", "untraceable number"),
    (" This happened because of a promotion.", "causal claim"),
    (" Top seller: Mumbai Reseller 1.", "raw reseller name"),
])
def test_output_guardrail_hard_stops(monkeypatch, suffix, needle):
    # GIVEN a drafting step that adds an invented number, a cause, or a raw reseller name
    real = narrative_generator.generate_narrative
    monkeypatch.setattr(runner, "generate_narrative", lambda row: real(row) + suffix)
    # WHEN the runner executes
    out = runner.run("May", FEED, FEED)
    # THEN the output guardrail hard-stops the run and no draft is returned
    assert out["action_taken"] == "hard_stop" and out["validation_status"] == "invalid"
    assert len(out["validation_errors"]) == 1 and needle in out["validation_errors"][0]
    assert out["validation_errors"][0].startswith("output guardrail:")
    assert out["flagged_categories"] == [] and out["suppressed_categories"] == []
    assert "Mumbai Reseller 1" not in json.dumps(out)


def test_no_message_is_sent():
    # GIVEN the runner module
    # WHEN its source is inspected
    source = open(runner.__file__, encoding="utf-8").read()
    # THEN it has no sending capability (Action guardrail): drafts are only held
    for forbidden in ("smtplib", "requests", "urllib", "http.client", "socket"):
        assert f"import {forbidden}" not in source
    assert runner.run("May", FEED, FEED)["action_taken"] == "drafted_and_held_for_approval"
