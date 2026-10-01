"""Given-When-Then tests for part3_narrative/narrative_generator.py (run with pytest)."""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from narrative_generator import build_narratives, generate_narrative  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "mom_growth_results.csv")


def _fixture_rows():
    with open(FIXTURE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _row(category, previous_month, month):
    return next(r for r in _fixture_rows()
                if (r["category"], r["previous_month"], r["month"]) == (category, previous_month, month))


def test_positive_growth_case():
    # GIVEN the April->May Ethnic Wear row (+77.1%, flagged)
    row = _row("Ethnic Wear", "April", "May")
    # WHEN its narrative is generated
    text = generate_narrative(row)
    # THEN it states an increase with the exact figures and the flagged result
    assert text == ("April -> May: Ethnic Wear revenue increased from INR 104520.77 to INR 185107.61, "
                    "a month-on-month change of 77.1%. Result: flagged - the change is beyond the 8% "
                    "threshold and needs attention.")


def test_negative_growth_case():
    # GIVEN the May->June Ethnic Wear row (-58.74%, flagged)
    row = _row("Ethnic Wear", "May", "June")
    # WHEN its narrative is generated
    text = generate_narrative(row)
    # THEN it states a decrease and keeps the negative sign exactly
    assert "decreased from INR 185107.61 to INR 76371.53" in text
    assert "-58.74%" in text
    assert "Result: flagged" in text
    assert "increased" not in text


def test_exact_boundary_case():
    # GIVEN a synthetic row exactly on the 8% boundary (100000 -> 108000)
    row = {"previous_month": "May", "month": "June", "category": "Synthetic Boundary",
           "previous_revenue": "100000", "current_revenue": "108000",
           "mom_pct": "8.0", "result": "escalate_exact_boundary"}
    # WHEN its narrative is generated
    text = generate_narrative(row)
    # THEN it is escalated for human review, not reported as flagged or not_flagged
    assert "8.0%" in text
    assert "Result: escalate_exact_boundary" in text
    assert "held for human review" in text
    assert "Result: flagged" not in text and "Result: not_flagged" not in text


def test_not_flagged_case():
    # GIVEN the May->June Beauty & Personal Care row (+5.67%, not_flagged)
    row = _row("Beauty & Personal Care", "May", "June")
    # WHEN its narrative is generated
    text = generate_narrative(row)
    # THEN it states an increase and the not_flagged result
    assert "increased from INR 35542.11 to INR 37559.07" in text
    assert "5.67%" in text
    assert "Result: not_flagged" in text


def test_one_narrative_per_input_row():
    # GIVEN the 10-row Part 2 fixture
    inputs = _fixture_rows()
    # WHEN narratives are built
    outputs = build_narratives(FIXTURE)
    # THEN there is exactly one non-empty narrative per input row
    assert len(outputs) == len(inputs) == 10
    assert all(o["narrative"] for o in outputs)


def test_input_ordering_preserved():
    # GIVEN the Part 2 fixture in its original order
    inputs = _fixture_rows()
    # WHEN narratives are built
    outputs = build_narratives(FIXTURE)
    # THEN month pairs, categories, figures and results appear in the same order, unchanged
    keys = ["previous_month", "month", "category", "previous_revenue", "current_revenue", "mom_pct", "result"]
    assert [[o[k] for k in keys] for o in outputs] == [[i[k] for k in keys] for i in inputs]
