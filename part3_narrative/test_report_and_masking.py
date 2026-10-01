"""Given-When-Then tests for masking.py, narrative_report.md and prompt_pack.md (run with pytest)."""

import csv
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from masking import alias_for, assert_no_raw_names_leak, require_no_raw_names_leak  # noqa: E402

REPORT = os.path.join(HERE, "narrative_report.md")
PROMPT_PACK = os.path.join(HERE, "prompt_pack.md")
MOM_FIXTURE = os.path.join(HERE, "fixtures", "mom_growth_results.csv")
RESELLERS_CSV = os.path.join(PROJECT_ROOT, "data", "resellers.csv")
TOP5_CSV = os.path.join(PROJECT_ROOT, "part1_sql", "output", "top5_resellers.csv")

CAUSAL_WORDS = ["because", "due to", "caused", "driven by", "as a result of", "owing to",
                "thanks to", "seasonal", "promotion", "festival", "demand", "pricing"]


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _reseller_names():
    return [r["reseller_name"] for r in _csv(RESELLERS_CSV)]


def _section(text, start_heading, end_heading):
    start = text.index(start_heading)
    end = text.index(end_heading, start + len(start_heading))
    return text[start:end]


def _labelled_lines(text, label):
    return [line for line in text.splitlines() if line.strip().startswith(f"- **{label}:**")]


# ---------------- masking ----------------

def test_alias_for_is_deterministic():
    # GIVEN a reseller ID
    # WHEN alias_for is called repeatedly
    aliases = {alias_for("RS019") for _ in range(5)}
    # THEN it always returns the same alias, matching the brief's examples
    assert aliases == {"ALIAS-19"}
    assert alias_for("RS006") == "ALIAS-06"


def test_different_ids_get_distinct_valid_aliases():
    # GIVEN all 24 reseller IDs from the dataset
    ids = [r["reseller_id"] for r in _csv(RESELLERS_CSV)]
    # WHEN each is aliased
    aliases = [alias_for(i) for i in ids]
    # THEN every alias has the ALIAS-NN form and no two resellers share one
    assert all(re.fullmatch(r"ALIAS-\d{2}", a) for a in aliases)
    assert len(set(aliases)) == len(ids) == 24


def test_no_leak_passes_when_names_absent():
    # GIVEN a masked sentence and the full list of raw reseller names
    text = "ALIAS-19 (West) had total spend of INR 75295.09."
    # WHEN the leak check runs
    # THEN it returns True and the strict variant does not raise
    assert assert_no_raw_names_leak(text, _reseller_names()) is True
    require_no_raw_names_leak(text, _reseller_names())


def test_leak_detected_when_raw_name_present():
    # GIVEN a version that still contains "Mumbai Reseller 1" verbatim
    text = "Mumbai Reseller 1 (West) had total spend of INR 75295.09."
    # WHEN the leak check runs
    # THEN it returns False and the strict variant raises AssertionError
    assert assert_no_raw_names_leak(text, _reseller_names()) is False
    with pytest.raises(AssertionError):
        require_no_raw_names_leak(text, _reseller_names())


def test_report_contains_no_raw_reseller_names():
    # GIVEN the final narrative report and all 24 raw reseller names
    # WHEN the leak check runs over the whole report
    # THEN no raw name leaks
    assert assert_no_raw_names_leak(_read(REPORT), _reseller_names()) is True


def test_top_reseller_narrative_uses_alias_and_region():
    # GIVEN Part 1's top-5 resellers and their regions
    region = {r["reseller_id"]: r["region"] for r in _csv(RESELLERS_CSV)}
    section = _read(REPORT).split("## Top-reseller narrative (masked)")[1]
    # WHEN the masked narrative is inspected
    # THEN each reseller appears as "alias (region): INR spend" in spend order
    positions = []
    for r in _csv(TOP5_CSV):
        entry = f"{alias_for(r['reseller_id'])} ({region[r['reseller_id']]}): INR {r['total_spend']}"
        assert entry in section
        positions.append(section.index(entry))
    assert positions == sorted(positions)


# ---------------- narrative report ----------------

@pytest.mark.parametrize("prev_month,month,heading,next_heading", [
    ("April", "May", "## Narrative 1", "## Narrative 2"),
    ("May", "June", "## Narrative 2", "## Self-scoring"),
])
def test_ethnic_wear_report_matches_part2_values(prev_month, month, heading, next_heading):
    # GIVEN the verified Part 2 Ethnic Wear row for this month pair
    row = next(r for r in _csv(MOM_FIXTURE)
               if (r["category"], r["previous_month"], r["month"]) == ("Ethnic Wear", prev_month, month))
    section = _section(_read(REPORT), heading, next_heading)
    insight = _section(section, "### Insight", "### Implication")
    # WHEN the Insight is read
    # THEN it carries the exact revenues, the MoM value (2 dp, sign kept), the raw
    #      Part 2 value, the result, and the correct direction
    pct = float(row["mom_pct"])
    assert f"INR {row['previous_revenue']}" in insight
    assert f"INR {row['current_revenue']}" in insight
    assert f"{pct:+.2f}%" in insight
    assert f"`mom_pct` = {row['mom_pct']}" in insight
    assert f"`{row['result']}`" in insight
    assert ("increased" if pct > 0 else "decreased") in insight
    assert f"{prev_month}" in section and f"{month}" in section


@pytest.mark.parametrize("heading,next_heading", [
    ("## Narrative 1", "## Narrative 2"),
    ("## Narrative 2", "## Self-scoring"),
])
def test_fact_and_hypothesis_are_distinguished(heading, next_heading):
    # GIVEN one Ethnic Wear narrative
    section = _section(_read(REPORT), heading, next_heading)
    # WHEN its sections and labels are inspected
    for sub in ("### Context", "### Insight", "### Implication"):
        assert sub in section
    bullets = [l for l in section.splitlines() if l.strip().startswith("- ")]
    # THEN every claim is explicitly labelled, the Insight is FACT,
    #      and the Implication holds a hedged HYPOTHESIS plus a concrete ACTION
    assert bullets and all(re.match(r"- \*\*(FACT|HYPOTHESIS|ACTION):\*\*", b.strip()) for b in bullets)
    insight = _section(section, "### Insight", "### Implication")
    assert _labelled_lines(insight, "FACT") and not _labelled_lines(insight, "HYPOTHESIS")
    implication = section.split("### Implication")[1]
    hyps = _labelled_lines(implication, "HYPOTHESIS")
    assert hyps and all(("cannot" in h or "not confirm" in h) for h in hyps)
    assert _labelled_lines(implication, "ACTION")


def test_no_causal_claim_presented_as_fact():
    # GIVEN every FACT statement in the report
    facts = _labelled_lines(_read(REPORT), "FACT")
    # WHEN they are scanned for causal / unsupported-cause wording
    offending = [f for f in facts if any(w in f.lower() for w in CAUSAL_WORDS)]
    # THEN none presents a cause as fact
    assert facts and offending == []


def test_report_has_self_scoring_and_chart_choice():
    # GIVEN the report
    text = _read(REPORT)
    # WHEN the required sections are looked up
    # THEN self-scoring covers every criterion for both narratives and all chart questions are answered
    scoring = _section(text, "## Self-scoring", "## Chart-choice")
    for criterion in ("Specificity", "Audience fit", "Completeness", "Actionability",
                      "Factual accuracy", "Hypothesis discipline", "Clarity"):
        assert scoring.count(f"| {criterion} |") == 2
    charts = _section(text, "## Chart-choice", "## Top-reseller")
    for q in ("Which month had the highest total revenue?",
              "What percentage share does Ethnic Wear represent of April's total revenue?",
              "How do the four regions compare on total revenue?"):
        assert q in charts
    for principle in ("10 seconds", "zero", "3D", "legend"):
        assert principle in charts


# ---------------- prompt pack ----------------

def test_prompt_pack_sections_and_checklist():
    # GIVEN the prompt pack
    text = _read(PROMPT_PACK)
    # WHEN its structure is inspected
    # THEN all four sections exist, every placeholder is listed, and the checklist has >= 4 items
    for heading in ("# Trigger", "# Inputs", "# Prompt", "# Checklist"):
        assert re.search(rf"^{heading}\s*$", text, re.M)
    for ph in ("{prev_month}", "{month}", "{category}", "{previous_revenue}",
               "{current_revenue}", "{mom_pct}", "{result}", "{direction}"):
        assert ph in text
    checklist = text.split("# Checklist")[1]
    assert len(re.findall(r"^\d+\. ", checklist, re.M)) >= 4
    for must in ("Context", "Insight", "Implication", "FACT", "HYPOTHESIS"):
        assert must in text
