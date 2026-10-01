"""Given-When-Then tests for part4_agent/agent.py (run with: python -m pytest part4_agent)."""

import csv
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, PROJECT_ROOT)

import agent  # noqa: E402
from part3_narrative import narrative_generator  # noqa: E402
from part3_narrative.masking import alias_for, assert_no_raw_names_leak  # noqa: E402

CAUSAL_WORDS = ("because", "due to", "caused", "driven by", "as a result of", "owing to",
                "promotion", "pricing", "demand", "seasonal", "competition")


def _csv(rel):
    with open(os.path.join(PROJECT_ROOT, rel), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _mom_row(category, previous_month, month):
    return next(r for r in _csv(agent.SOURCES[agent.MOM_GROWTH])
                if (r["category"], r["previous_month"], r["month"]) == (category, previous_month, month))


def _raw_names():
    return [r["reseller_name"] for r in _csv("data/resellers.csv")]


# ---------------- 1-6: routing ----------------

@pytest.mark.parametrize("question,intent", [
    ("What was the revenue for Ethnic Wear in May?", agent.MONTHLY_CATEGORY_REVENUE),
    ("Which region had the highest revenue?", agent.REGION_REVENUE),
    ("Who are the top 5 resellers?", agent.TOP_RESELLERS),
    ("Which reseller never placed an order?", agent.ZERO_ORDER_RESELLERS),
    ("What is the June delivered average order value?", agent.JUNE_DELIVERED_AOV),
    ("How did Ethnic Wear change from April to May?", agent.MOM_GROWTH),
])
def test_routing(question, intent):
    # GIVEN a supported business question
    # WHEN it is routed (twice, to prove the result is stable)
    first, second = agent.route_question(question), agent.route_question(question)
    # THEN it maps to the expected intent identifier every time
    assert first == second == intent


def test_monthly_revenue_answer_comes_from_part1_csv():
    # GIVEN the verified Part 1 row for Ethnic Wear in May
    row = next(r for r in _csv(agent.SOURCES[agent.MONTHLY_CATEGORY_REVENUE])
               if (r["month"], r["category"]) == ("May", "Ethnic Wear"))
    # WHEN the agent answers the revenue question
    resp = agent.answer("What was the revenue for Ethnic Wear in May?")
    # THEN it reports that row's exact revenue and order count, citing the Part 1 source
    assert resp["status"] == "ok"
    assert f"INR {row['revenue']}" in resp["answer"] and row["n_orders"] in resp["answer"]
    assert resp["source"] == agent.SOURCES[agent.MONTHLY_CATEGORY_REVENUE]


def test_region_highest_answer_comes_from_part1_csv():
    # GIVEN the verified region CSV
    top = max(_csv(agent.SOURCES[agent.REGION_REVENUE]), key=lambda r: float(r["total_revenue"]))
    # WHEN the agent is asked which region had the highest revenue
    resp = agent.answer("Which region had the highest revenue?")
    # THEN it names that region with its exact revenue and order count
    assert resp["status"] == "ok"
    assert top["region"] in resp["answer"] and f"INR {top['total_revenue']}" in resp["answer"]
    assert top["n_orders"] in resp["answer"]


def test_june_aov_answer_comes_from_part1_csv():
    # GIVEN the verified June Delivered AOV CSV
    aov = _csv(agent.SOURCES[agent.JUNE_DELIVERED_AOV])[0]["aov"]
    # WHEN the agent is asked for it
    resp = agent.answer("What is the June delivered average order value?")
    # THEN it reports that exact value and states the Delivered-only scope
    assert resp["status"] == "ok"
    assert f"INR {aov}" in resp["answer"] and "Delivered" in resp["answer"]


# ---------------- 7: narrative generator integration ----------------

def test_mom_route_calls_part3_generate_narrative(monkeypatch):
    # GIVEN a spy wrapped around the real Part 3 generate_narrative
    calls = []
    real = narrative_generator.generate_narrative

    def spy(row):
        calls.append(dict(row))
        return real(row)

    monkeypatch.setattr(agent, "generate_narrative", spy)
    # WHEN a MoM question is answered
    resp = agent.answer("How did Ethnic Wear change from April to May?")
    # THEN Part 3's function was called exactly once, with the verified Part 2 row,
    #      and the answer IS its output (not a re-implemented sentence)
    expected_row = _mom_row("Ethnic Wear", "April", "May")
    assert calls == [expected_row]
    assert resp["answer"] == real(expected_row)
    assert agent.NARRATIVE_FUNCTION in resp["source"]


def test_agent_imports_the_part3_function_itself():
    # GIVEN the agent module
    # WHEN its generate_narrative reference is inspected
    # THEN it is the very function defined in part3_narrative/narrative_generator.py
    assert agent.generate_narrative is narrative_generator.generate_narrative


# ---------------- 8-10: exact numbers, sign, result ----------------

@pytest.mark.parametrize("question,category,prev,month,direction", [
    ("How did Ethnic Wear change from April to May?", "Ethnic Wear", "April", "May", "increased"),
    ("How did Ethnic Wear change from May to June?", "Ethnic Wear", "May", "June", "decreased"),
    ("How did Beauty & Personal Care change from May to June?", "Beauty & Personal Care", "May", "June", "increased"),
])
def test_mom_values_match_part2_csv(question, category, prev, month, direction):
    # GIVEN the verified Part 2 row for this category and month pair
    row = _mom_row(category, prev, month)
    # WHEN the agent answers the growth question
    text = agent.answer(question)["answer"]
    # THEN every value from that row appears verbatim, sign and result included
    for col in ("previous_month", "month", "category", "previous_revenue", "current_revenue", "result"):
        assert row[col] in text
    assert f"change of {row['mom_pct']}%" in text
    assert direction in text


def test_ethnic_wear_april_may_exact_values():
    # GIVEN the April->May Ethnic Wear question
    text = agent.answer("How did Ethnic Wear change from April to May?")["answer"]
    row = _mom_row("Ethnic Wear", "April", "May")
    # WHEN compared with the brief's acceptance values AND the Part 2 CSV
    # THEN both agree
    for v in ("104520.77", "185107.61", "77.1", "flagged"):
        assert v in text and v in row.values()


def test_ethnic_wear_may_june_negative_growth():
    # GIVEN the May->June Ethnic Wear question
    text = agent.answer("How did Ethnic Wear change from May to June?")["answer"]
    row = _mom_row("Ethnic Wear", "May", "June")
    # WHEN the answer is inspected
    # THEN the negative MoM sign is preserved and the values come from Part 2
    for v in ("185107.61", "76371.53", "-58.74", "flagged"):
        assert v in text and v in row.values()
    assert "decreased" in text


def test_beauty_may_june_not_flagged():
    # GIVEN the May->June Beauty & Personal Care question
    text = agent.answer("How did Beauty & Personal Care change from May to June?")["answer"]
    row = _mom_row("Beauty & Personal Care", "May", "June")
    # WHEN the answer is inspected
    # THEN the not_flagged result is preserved
    assert "5.67" in text and row["mom_pct"] == "5.67"
    assert "not_flagged" in text and row["result"] == "not_flagged"


# ---------------- 11-13: safe rejection ----------------

def test_unsupported_question_is_rejected():
    # GIVEN a question outside the verified data
    resp = agent.answer("Tell me tomorrow's sales.")
    # WHEN answered
    # THEN the agent returns the controlled unsupported message and no source or numbers
    assert resp["intent"] == "unsupported" and resp["status"] == "unsupported"
    assert resp["answer"] == agent.UNSUPPORTED_MESSAGE
    assert resp["source"] is None
    assert agent.format_response(resp).startswith("Intent:\nunsupported\n\nAnswer:\n")


def test_invalid_category_is_rejected():
    # GIVEN a category that does not exist in the data
    resp = agent.answer("What was the revenue for Electronics in May?")
    # WHEN answered
    # THEN a controlled validation error is returned and no category is substituted
    assert resp["status"] == "validation_error"
    assert "not in the verified data" in resp["answer"]
    assert "INR" not in resp["answer"]


def test_invalid_month_is_rejected():
    # GIVEN a month that does not exist in the data
    resp = agent.answer("What was the revenue for Ethnic Wear in January?")
    # WHEN answered
    # THEN a controlled validation error is returned and no month is substituted
    assert resp["status"] == "validation_error"
    assert "January" in resp["answer"] and "INR" not in resp["answer"]


def test_non_adjacent_month_pair_is_rejected():
    # GIVEN April->June, which Part 2 deliberately never compares
    resp = agent.answer("How did Ethnic Wear change from April to June?")
    # WHEN answered
    # THEN it is rejected rather than computed
    assert resp["status"] == "validation_error"
    assert "No verified month-over-month comparison" in resp["answer"]


def test_untraceable_number_is_withheld():
    # GIVEN an answer containing a number that is not in its source rows
    rows = [{"revenue": "100.00"}]
    # WHEN the number guardrail runs
    # THEN it raises instead of letting the figure through
    with pytest.raises(agent.ValidationError):
        agent._validate_numbers("Revenue was INR 999.99.", rows)
    agent._validate_numbers("Revenue was INR 100.00.", rows)


# ---------------- 14: no fabricated causes ----------------

def test_why_question_separates_fact_from_hypothesis():
    # GIVEN a "why" question about a revenue drop
    resp = agent.answer("Why did Ethnic Wear revenue drop in June?")
    lines = resp["answer"].splitlines()
    facts = [l for l in lines if l.startswith("FACT:")]
    hyps = [l for l in lines if l.startswith("HYPOTHESIS:")]
    # WHEN the answer is inspected
    # THEN the FACT is the verified Part 3 narrative with no causal wording,
    #      and any explanation is labelled HYPOTHESIS and marked unconfirmed
    assert resp["status"] == "ok"
    assert facts == [f"FACT: {narrative_generator.generate_narrative(_mom_row('Ethnic Wear', 'May', 'June'))}"]
    assert not any(w in f.lower() for f in facts for w in CAUSAL_WORDS)
    assert hyps and all("not confirmed" in h for h in hyps)
    assert any(l.startswith("ACTION:") for l in lines)


def test_no_causal_words_in_any_mom_answer():
    # GIVEN every MoM row in the verified Part 2 output
    for r in _csv(agent.SOURCES[agent.MOM_GROWTH]):
        # WHEN the agent answers a plain growth question for it
        text = agent.answer(f"How did {r['category']} change from {r['previous_month']} to {r['month']}?")["answer"]
        # THEN no cause is asserted
        assert not any(w in text.lower() for w in CAUSAL_WORDS), text


# ---------------- 15: masking ----------------

def test_top_resellers_masked():
    # GIVEN the verified top-5 output (which contains raw names)
    rows = _csv(agent.SOURCES[agent.TOP_RESELLERS])
    region = {r["reseller_id"]: r["region"] for r in _csv("data/resellers.csv")}
    # WHEN the agent answers
    text = agent.answer("Who are the top 5 resellers?")["answer"]
    # THEN each reseller appears only as alias (region) with exact spend, in order, and no raw name leaks
    positions = []
    for r in rows:
        entry = f"{alias_for(r['reseller_id'])} ({region[r['reseller_id']]}): INR {r['total_spend']}"
        assert entry in text
        assert r["reseller_name"] not in text
        positions.append(text.index(entry))
    assert positions == sorted(positions)
    assert assert_no_raw_names_leak(text, _raw_names()) is True


def test_zero_order_reseller_masked():
    # GIVEN the verified zero-order output (one reseller, with its raw name)
    row = _csv(agent.SOURCES[agent.ZERO_ORDER_RESELLERS])[0]
    # WHEN the agent answers
    text = agent.answer("Which reseller never placed an order?")["answer"]
    # THEN it is reported by alias and region only
    assert f"{alias_for(row['reseller_id'])} ({row['region']})" in text
    assert row["reseller_name"] not in text
    assert assert_no_raw_names_leak(text, _raw_names()) is True


def test_leak_guard_blocks_raw_names(monkeypatch):
    # GIVEN a handler that would (wrongly) include a raw reseller name
    leaky = lambda q: ("Mumbai Reseller 1 is the top reseller.", [], (), "test")  # noqa: E731
    monkeypatch.setitem(agent.HANDLERS, agent.TOP_RESELLERS, leaky)
    # WHEN the agent answers
    resp = agent.answer("Who are the top 5 resellers?")
    # THEN the answer is withheld instead of leaking the name
    assert resp["status"] == "validation_error"
    assert "Mumbai Reseller 1" not in resp["answer"]


# ---------------- fixture-driven verification ----------------

def test_fixture_questions_all_pass(tmp_path):
    # GIVEN every question in fixtures/agent_questions.json
    # WHEN the verification run executes (written to a temp file, not the real output)
    report = agent.run_verification(agent.DEFAULT_QUESTIONS, str(tmp_path / "results.json"))
    # THEN every case passes and all intents are exercised
    failed = [r for r in report["results"] if not r["passed"]]
    assert failed == [], json.dumps(failed, indent=2)
    seen = {r["detected_intent"] for r in report["results"]}
    assert seen == set(agent.HANDLERS) | {"unsupported"}
