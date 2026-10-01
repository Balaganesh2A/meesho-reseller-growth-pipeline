"""Part 4 - Offline question-routing agent over the verified Parts 1-3 outputs.

Deterministic, standard library only, no LLM/API. For each question the agent:

  1. routes it to one supported intent with keyword/pattern rules (route_question),
  2. validates every requested month / category / region / reseller against the
     verified source CSV (never substituting a different one),
  3. answers only from rows of that CSV - for MOM_GROWTH the text is drafted by
     Part 3's narrative_generator.generate_narrative,
  4. checks that every number in the answer appears in the source rows it used,
     and that no raw reseller name leaks (Part 3 masking),
  5. returns {intent, status, answer, source}; format_response() renders it.

Status values: "ok", "validation_error", "unsupported".

Usage:
    python part4_agent/agent.py "How did Ethnic Wear change from April to May?"
    python part4_agent/agent.py --verify     # runs fixtures/agent_questions.json
"""

import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from part3_narrative.masking import alias_for, assert_no_raw_names_leak, require_no_raw_names_leak  # noqa: E402
from part3_narrative.narrative_generator import generate_narrative  # noqa: E402

MONTHLY_CATEGORY_REVENUE = "MONTHLY_CATEGORY_REVENUE"
REGION_REVENUE = "REGION_REVENUE"
TOP_RESELLERS = "TOP_RESELLERS"
ZERO_ORDER_RESELLERS = "ZERO_ORDER_RESELLERS"
JUNE_DELIVERED_AOV = "JUNE_DELIVERED_AOV"
MOM_GROWTH = "MOM_GROWTH"
UNSUPPORTED = "unsupported"

SOURCES = {
    MONTHLY_CATEGORY_REVENUE: "part1_sql/output/monthly_category_revenue.csv",
    REGION_REVENUE: "part1_sql/output/region_revenue.csv",
    TOP_RESELLERS: "part1_sql/output/top5_resellers.csv",
    ZERO_ORDER_RESELLERS: "part1_sql/output/zero_order_resellers.csv",
    JUNE_DELIVERED_AOV: "part1_sql/output/june_delivered_aov.csv",
    MOM_GROWTH: "part2_engine/output/mom_growth_results.csv",
}
RESELLERS_SOURCE = "data/resellers.csv"  # read-only: regions and the raw names to mask
NARRATIVE_FUNCTION = "part3_narrative.narrative_generator.generate_narrative"

DEFAULT_QUESTIONS = os.path.join(HERE, "fixtures", "agent_questions.json")
DEFAULT_RESULTS = os.path.join(HERE, "output", "agent_test_results.json")

UNSUPPORTED_MESSAGE = ("Unsupported or ambiguous question. Please ask about revenue, regional revenue, "
                       "top resellers, zero-order resellers, June delivered AOV, or month-over-month "
                       "category growth.")

# Parsing vocabulary only - which months/categories/regions exist is always read from the data.
CALENDAR_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"]
FORECAST_TERMS = ("tomorrow", "next week", "next month", "next quarter", "next year",
                  "forecast", "predict", "prediction", "projection", "will be", "going to")
ZERO_ORDER_TERMS = ("never", "no order", "no orders", "zero order", "zero orders", "zero-order",
                    "not placed", "did not place", "didn't place", "hasn't placed", "haven't placed",
                    "without an order", "without any order", "without orders", "inactive")
AOV_TERMS = ("aov", "average order value", "average order")
TOP_TERMS = ("top", "best", "highest", "biggest", "largest", "most", "spend", "spending", "rank", "ranking")
MOM_TERMS = ("change", "changed", "growth", "grow", "grew", "mom", "month-over-month", "month over month",
             "month-on-month", "month on month", "increase", "increased", "decrease", "decreased",
             "drop", "dropped", "fall", "fell", "rise", "rose", "decline", "declined", "trend",
             "compare", "compared", "versus", "vs", "flagged", "why")
REVENUE_TERMS = ("revenue", "sales", "earn", "earned", "made", "income")
HIGH_TERMS = ("highest", "most", "top", "best", "largest", "biggest", "leading")
LOW_TERMS = ("lowest", "least", "smallest", "worst", "weakest", "bottom")
OTHER_STATUSES = ("returned", "cancelled", "canceled", "pending")
GENERIC_PHRASES = {"revenue", "sales", "total revenue", "overall revenue", "it", "category", "categories",
                   "each category", "every category", "all categories", "the category", "business",
                   "things", "overall"}
REGION_WORD_STOPWORDS = {"which", "each", "every", "the", "a", "per", "what", "that", "this", "any",
                         "one", "top", "best", "highest", "lowest", "my", "our", "by"}

WHY_HYPOTHESIS = ("HYPOTHESIS: The supplied data does not record causes (such as promotions, pricing, "
                  "demand, seasonality or competition), so none is stated as fact. One possibility to "
                  "test is that the change is concentrated in a few resellers; this is not confirmed "
                  "by the supplied data.")
WHY_ACTION = ("ACTION: Break the orders for this category and month pair down by reseller "
              "(data/orders.csv joined to data/resellers.csv) to test that hypothesis before acting.")


class ValidationError(Exception):
    """A request that cannot be answered safely from the verified data."""


# ---------------------------------------------------------------- helpers

def _read_csv(rel_path):
    with open(os.path.join(PROJECT_ROOT, rel_path), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _has(text, terms):
    return any(re.search(r"(?<![\w-])" + re.escape(t) + r"(?![\w-])", text) for t in terms)


def _unique(values):
    out = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def _find_months(question):
    """Calendar months named in the question, in order of appearance.

    "May" must be capitalised so the modal verb "may" is not read as a month.
    """
    found = []
    for m in CALENDAR_MONTHS:
        flags = 0 if m == "May" else re.I
        hit = re.search(rf"\b{m}\b", question, flags)
        if hit:
            found.append((hit.start(), m))
    return [m for _, m in sorted(found)]


def _find_categories(question, categories):
    q = question.lower().replace(" and ", " & ")
    return [c for c in categories if re.search(r"\b" + re.escape(c.lower()) + r"\b", q)]


def _candidate_category(question):
    """A category-like phrase the user asked about, if no known category matched."""
    q = question.lower()
    patterns = [
        r"\b(?:for|of)\s+([a-z][a-z&' -]*?)\s+(?:in|during|from|between)\b",
        r"\b(?:did|has|have|was|were)\s+([a-z][a-z&' -]*?)\s+(?:revenue\s+|sales\s+)?"
        r"(?:change|changed|grow|grew|move|moved|drop|dropped|fall|fell|rise|rose|increase|"
        r"increased|decrease|decreased|decline|declined|do|perform)\b",
    ]
    for p in patterns:
        m = re.search(p, q)
        if m:
            # Match on lower case, but echo the user's own wording back in the error.
            phrase = re.sub(r"^the\s+", "", question[m.start(1):m.end(1)].strip(), flags=re.I)
            if phrase and phrase.lower() not in GENERIC_PHRASES:
                return phrase
    return None


def _resolve_category(question, categories):
    found = _find_categories(question, categories)
    if len(found) > 1:
        raise ValidationError(f"Please ask about one category at a time (found: {', '.join(found)}).")
    if found:
        return found[0]
    candidate = _candidate_category(question)
    if candidate:
        raise ValidationError(f"Category '{candidate}' is not in the verified data. "
                              f"Available categories: {', '.join(categories)}.")
    return None


def _check_months_exist(months, available):
    for m in months:
        if m not in available:
            raise ValidationError(f"Month '{m}' is not in the verified data. "
                                  f"Available months: {', '.join(available)}.")


def _resellers():
    return {r["reseller_id"]: r for r in _read_csv(RESELLERS_SOURCE)}


def _requested_reseller_ids(question, resellers):
    ids = _unique(re.findall(r"\bRS\d{3}\b", question.upper()))
    for rid in ids:
        if rid not in resellers:
            raise ValidationError(f"Reseller '{rid}' does not exist in the verified data.")
    return ids


def _validate_numbers(text, rows, extra_allowed=()):
    """Every number in the answer must be a verbatim value of a source row it used."""
    allowed = {v for row in rows for v in row.values()} | set(extra_allowed)
    cleaned = re.sub(r"ALIAS-\d+", "", text)
    untraceable = [n for n in re.findall(r"-?\d+(?:\.\d+)?", cleaned) if n not in allowed]
    if untraceable:
        raise ValidationError("Answer withheld: number(s) not traceable to the verified source: "
                              + ", ".join(untraceable))


def _masked(rid, resellers):
    return f"{alias_for(rid)} ({resellers[rid]['region']})"


# ---------------------------------------------------------------- routing

def route_question(question):
    """Return a stable intent identifier for the question, or "unsupported"."""
    q = question.lower()
    if _has(q, FORECAST_TERMS):
        return UNSUPPORTED
    if _has(q, ZERO_ORDER_TERMS):
        return ZERO_ORDER_RESELLERS
    if _has(q, AOV_TERMS):
        return JUNE_DELIVERED_AOV
    if "reseller" in q and _has(q, TOP_TERMS):
        return TOP_RESELLERS
    if _has(q, MOM_TERMS) or len(_find_months(question)) >= 2:
        return MOM_GROWTH
    if "region" in q or _has(q, ("north", "south", "east", "west")):
        return REGION_REVENUE
    if _has(q, REVENUE_TERMS):
        categories = _unique(r["category"] for r in _read_csv(SOURCES[MONTHLY_CATEGORY_REVENUE]))
        if _find_categories(question, categories) or _find_months(question) or _candidate_category(question):
            return MONTHLY_CATEGORY_REVENUE
    return UNSUPPORTED


# ---------------------------------------------------------------- handlers
# Each returns (answer_text, source_rows_used, extra_allowed_numbers, source_description).

def _handle_monthly_revenue(question):
    rows = _read_csv(SOURCES[MONTHLY_CATEGORY_REVENUE])
    months = _unique(r["month"] for r in rows)
    categories = _unique(r["category"] for r in rows)
    asked_months = _find_months(question)
    _check_months_exist(asked_months, months)
    if len(asked_months) > 1:
        raise ValidationError("Please ask about one month at a time.")
    category = _resolve_category(question, categories)
    month = asked_months[0] if asked_months else None
    if not category and not month:
        raise ValidationError("Please specify a category and/or a month (April, May or June).")
    selected = [r for r in rows if (not month or r["month"] == month) and (not category or r["category"] == category)]
    text = "\n".join(f"{r['category']} revenue in {r['month']} was INR {r['revenue']} from {r['n_orders']} orders."
                     for r in selected)
    return text, selected, (), SOURCES[MONTHLY_CATEGORY_REVENUE]


def _handle_region_revenue(question):
    rows = _read_csv(SOURCES[REGION_REVENUE])
    regions = [r["region"] for r in rows]
    for word in re.findall(r"\b([A-Za-z]+)\s+region\b", question):
        if word.lower() not in {r.lower() for r in regions} and word.lower() not in REGION_WORD_STOPWORDS:
            raise ValidationError(f"Region '{word}' is not in the verified data. "
                                  f"Available regions: {', '.join(regions)}.")
    q = question.lower()
    named = [r for r in rows if re.search(rf"\b{r['region'].lower()}\b", q)]
    if named:
        selected = named
        text = "\n".join(f"{r['region']} total revenue was INR {r['total_revenue']} from {r['n_orders']} orders."
                         for r in named)
    elif _has(q, HIGH_TERMS):
        r = max(rows, key=lambda x: float(x["total_revenue"]))
        selected = [r]
        text = f"{r['region']} had the highest total revenue: INR {r['total_revenue']} from {r['n_orders']} orders."
    elif _has(q, LOW_TERMS):
        r = min(rows, key=lambda x: float(x["total_revenue"]))
        selected = [r]
        text = f"{r['region']} had the lowest total revenue: INR {r['total_revenue']} from {r['n_orders']} orders."
    else:
        selected = rows
        text = "\n".join(f"{r['region']}: INR {r['total_revenue']} ({r['n_orders']} orders)" for r in rows)
    return text, selected, (), SOURCES[REGION_REVENUE]


def _handle_top_resellers(question):
    rows = _read_csv(SOURCES[TOP_RESELLERS])
    resellers = _resellers()
    in_top = [r["reseller_id"] for r in rows]
    asked_ids = _requested_reseller_ids(question, resellers)
    if asked_ids:
        selected = []
        for rid in asked_ids:
            if rid not in in_top:
                raise ValidationError(f"Reseller '{rid}' is not in the verified top-resellers output.")
            selected.append(next(r for r in rows if r["reseller_id"] == rid))
    else:
        n = re.search(r"\btop\s+(\d+)\b", question.lower())
        count = int(n.group(1)) if n else len(rows)
        if count < 1 or count > len(rows):
            raise ValidationError(f"The verified output ranks only {len(rows)} resellers.")
        selected = rows[:count]
    lines = ["Top resellers by total spend, highest first (shown by alias and region only):"]
    lines += [f"{_masked(r['reseller_id'], resellers)}: INR {r['total_spend']}" for r in selected]
    return "\n".join(lines), selected, (), SOURCES[TOP_RESELLERS]


def _handle_zero_order(question):
    rows = _read_csv(SOURCES[ZERO_ORDER_RESELLERS])
    resellers = _resellers()
    zero_ids = [r["reseller_id"] for r in rows]
    asked_ids = _requested_reseller_ids(question, resellers)
    if asked_ids:
        lines = [f"{_masked(rid, resellers)} " + ("has never placed an order."
                 if rid in zero_ids else "is not in the verified zero-order list.") for rid in asked_ids]
    elif rows:
        lines = [f"{_masked(r['reseller_id'], resellers)} has never placed an order." for r in rows]
    else:
        lines = ["No reseller in the verified output has zero orders."]
    return "\n".join(lines), rows, (), SOURCES[ZERO_ORDER_RESELLERS]


def _handle_june_aov(question):
    rows = _read_csv(SOURCES[JUNE_DELIVERED_AOV])
    other_months = [m for m in _find_months(question) if m != "June"]
    if other_months:
        raise ValidationError(f"Only the June Delivered AOV is available in the verified outputs "
                              f"(asked about: {', '.join(other_months)}).")
    if _has(question.lower(), OTHER_STATUSES):
        raise ValidationError("Only the AOV for Delivered orders is available in the verified outputs.")
    text = f"June average order value for Delivered orders was INR {rows[0]['aov']}."
    return text, rows, (), SOURCES[JUNE_DELIVERED_AOV]


def _handle_mom_growth(question):
    rows = _read_csv(SOURCES[MOM_GROWTH])
    pairs = _unique((r["previous_month"], r["month"]) for r in rows)
    months = _unique([m for p in pairs for m in p])
    categories = _unique(r["category"] for r in rows)
    asked_months = _find_months(question)
    _check_months_exist(asked_months, months)
    available = ", ".join(f"{a} -> {b}" for a, b in pairs)
    if len(asked_months) > 2:
        raise ValidationError("Please ask about one month pair at a time.")
    if len(asked_months) == 2:
        if tuple(asked_months) not in pairs:
            raise ValidationError(f"No verified month-over-month comparison for {asked_months[0]} -> "
                                  f"{asked_months[1]}. Available comparisons: {available}.")
        wanted = [tuple(asked_months)]
    elif len(asked_months) == 1:
        wanted = [p for p in pairs if p[1] == asked_months[0]]
        if not wanted:
            raise ValidationError(f"{asked_months[0]} has no previous month in the verified data. "
                                  f"Available comparisons: {available}.")
    else:
        wanted = pairs
    category = _resolve_category(question, categories)
    selected = [r for r in rows if (r["previous_month"], r["month"]) in wanted
                and (not category or r["category"] == category)]

    narratives = [generate_narrative(r) for r in selected]
    if _has(question.lower(), ("why",)):
        text = "\n".join([f"FACT: {n}" for n in narratives] + [WHY_HYPOTHESIS, WHY_ACTION])
    else:
        text = "\n".join(narratives)
    source = f"{SOURCES[MOM_GROWTH]} (narrative drafted by {NARRATIVE_FUNCTION})"
    # The narrative template states the Part 2 threshold ("8%"), so that number is allowed too.
    return text, selected, ("8",), source


HANDLERS = {
    MONTHLY_CATEGORY_REVENUE: _handle_monthly_revenue,
    REGION_REVENUE: _handle_region_revenue,
    TOP_RESELLERS: _handle_top_resellers,
    ZERO_ORDER_RESELLERS: _handle_zero_order,
    JUNE_DELIVERED_AOV: _handle_june_aov,
    MOM_GROWTH: _handle_mom_growth,
}


# ---------------------------------------------------------------- public API

def answer(question):
    """Route, validate and answer one question. Returns {intent, status, answer, source}."""
    intent = route_question(question)
    if intent == UNSUPPORTED:
        return {"intent": UNSUPPORTED, "status": "unsupported", "answer": UNSUPPORTED_MESSAGE, "source": None}
    try:
        text, rows, extra, source = HANDLERS[intent](question)
        _validate_numbers(text, rows, extra)
        try:
            names = [r["reseller_name"] for r in _resellers().values()]
            require_no_raw_names_leak(text, names)
        except AssertionError:
            raise ValidationError("Answer withheld: masking check failed (raw reseller name present).")
    except ValidationError as e:
        return {"intent": intent, "status": "validation_error", "answer": str(e), "source": SOURCES[intent]}
    return {"intent": intent, "status": "ok", "answer": text, "source": source}


def format_response(resp):
    lines = ["Intent:", resp["intent"], "", "Answer:", resp["answer"]]
    if resp.get("source"):
        lines += ["", "Source:", resp["source"]]
    return "\n".join(lines)


# ---------------------------------------------------------------- verification run

FACT_CAUSAL_WORDS = ("because", "due to", "caused", "driven by", "as a result of", "owing to",
                     "promotion", "pricing", "demand", "seasonal", "competition")


def _select_rows(intent, spec):
    rows = _read_csv(SOURCES[intent])
    if "row_select" in spec:
        kind, col = spec["row_select"].split(":")
        pick = max if kind == "max" else min
        return [pick(rows, key=lambda r: float(r[col]))]
    flt = spec.get("row_filter", {})
    return [r for r in rows if all(r[k] == v for k, v in flt.items())]


def verify_case(case):
    """Run one fixture case and return a JSON-serialisable result record."""
    resp = answer(case["question"])
    text = resp["answer"]
    checks = {
        "intent": resp["intent"] == case["expected_intent"],
        "status": resp["status"] == case["expected_status"],
        "no_raw_name_leak": assert_no_raw_names_leak(text, [r["reseller_name"] for r in _resellers().values()]),
        "no_causal_fact": not any(w in line.lower() for line in text.splitlines()
                                  if line.startswith("FACT:") for w in FACT_CAUSAL_WORDS),
    }
    if resp["status"] == "ok" and ("row_filter" in case or "row_select" in case):
        rows = _select_rows(resp["intent"], case)
        fields = case.get("check_fields", [])
        checks["source_rows_found"] = bool(rows)
        checks["source_values_in_answer"] = bool(rows) and all(r[f] in text for r in rows for f in fields)
        if resp["intent"] in (TOP_RESELLERS, ZERO_ORDER_RESELLERS):
            checks["aliases_in_answer"] = all(alias_for(r["reseller_id"]) in text for r in rows)
        if resp["intent"] == MOM_GROWTH:
            checks["uses_generate_narrative"] = all(generate_narrative(r) in text for r in rows)
    for s in case.get("must_contain", []):
        checks[f"contains:{s}"] = s in text
    for s in case.get("must_not_contain", []):
        checks[f"excludes:{s}"] = s not in text
    failed = [k for k, v in checks.items() if not v]
    return {
        "id": case["id"],
        "question": case["question"],
        "expected_intent": case["expected_intent"],
        "detected_intent": resp["intent"],
        "validation_status": resp["status"],
        "source": resp["source"],
        "passed": not failed,
        "verification": f"all {len(checks)} checks passed" if not failed else "failed: " + ", ".join(failed),
        "answer": text,
    }


def run_verification(questions_path=DEFAULT_QUESTIONS, out_path=DEFAULT_RESULTS):
    with open(questions_path, encoding="utf-8") as f:
        cases = json.load(f)["questions"]
    results = [verify_case(c) for c in cases]
    report = {
        "summary": {"total": len(results), "passed": sum(r["passed"] for r in results),
                    "failed": sum(not r["passed"] for r in results)},
        "results": results,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return report


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        rep = run_verification()
        for r in rep["results"]:
            print(f"[{'PASS' if r['passed'] else 'FAIL'}] {r['detected_intent']:<26} {r['validation_status']:<17} {r['question']}")
        print(f"\n{rep['summary']['passed']}/{rep['summary']['total']} passed -> {DEFAULT_RESULTS}")
    elif len(sys.argv) > 1:
        print(format_response(answer(" ".join(sys.argv[1:]))))
    else:
        print(__doc__)
