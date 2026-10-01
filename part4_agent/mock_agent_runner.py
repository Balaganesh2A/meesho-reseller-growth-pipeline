"""Part 4 - Mock agent runner (assignment section 4.4).

    run(month, previous_month_csv, current_month_csv) -> dict

Executes the Planner from agent_spec.md (subtasks 1-8) fully offline, using:
  * Part 2's growth_engine.validate_feed / mom_growth / is_flagged, imported unmodified;
  * Part 3's narrative_generator.generate_narrative for every drafted message;
  * Part 3's masking.require_no_raw_names_leak as an output check.

Both CSVs use Part 1's month,category,revenue,n_orders schema; they may be the
same file (Part 1's monthly_category_revenue.csv holds all three months). The
runner uses the `month` rows of current_month_csv and the rows for the calendar
month before `month` from previous_month_csv.

Returns exactly the seven keys of section 4.3 and never sends anything:
drafts are held for human approval.

Usage:
    python part4_agent/mock_agent_runner.py May
    python part4_agent/mock_agent_runner.py July part1_sql/output/monthly_category_revenue.csv part2_engine/fixtures/corrupted_feed.csv
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

from part2_engine.growth_engine import is_flagged, mom_growth, validate_feed  # noqa: E402
from part3_narrative.masking import require_no_raw_names_leak  # noqa: E402
from part3_narrative.narrative_generator import generate_narrative  # noqa: E402

DEFAULT_FEED = os.path.join(PROJECT_ROOT, "part1_sql", "output", "monthly_category_revenue.csv")
RESELLERS_CSV = os.path.join(PROJECT_ROOT, "data", "resellers.csv")  # read-only, for the leak check

THRESHOLD = 8.0
DRAFT_CAP = 3  # subtask 6: prevents notification flooding
CALENDAR_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"]
OUTPUT_KEYS = ("run_month", "validation_status", "validation_errors", "flagged_categories",
               "suppressed_categories", "escalated_categories", "action_taken")
CAUSAL_WORDS = ("because", "due to", "caused", "driven by", "as a result of", "owing to",
                "promotion", "pricing", "demand", "seasonal", "competition")


class GuardrailError(Exception):
    """A check after validation failed; the run must stop, not return partial output."""


def _result(month, status, errors, flagged, suppressed, escalated, action):
    out = {
        "run_month": month,
        "validation_status": status,
        "validation_errors": errors,
        "flagged_categories": flagged,
        "suppressed_categories": suppressed,
        "escalated_categories": escalated,
        "action_taken": action,
    }
    assert tuple(out) == OUTPUT_KEYS
    return out


def _hard_stop(month, errors):
    return _result(month, "invalid", list(errors), [], [], [], "hard_stop")


def _rows_for(csv_path, month):
    """{category: revenue string} for one month, in feed order (verbatim strings)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {r["category"]: r["revenue"] for r in csv.DictReader(f) if r["month"] == month}


def _check_message(message, row, raw_names):
    """Output guardrail on one drafted message (raises GuardrailError on any failure).

    The name-leak check runs first so a leaked name is reported as a leak, not as stray digits.
    """
    try:
        require_no_raw_names_leak(message, raw_names)
    except AssertionError:
        raise GuardrailError(f"output guardrail: raw reseller name in message for {row['category']}")
    if row["category"] not in message or f"{row['mom_pct']}%" not in message:
        raise GuardrailError(f"output guardrail: message for {row['category']} lacks its category or exact mom_pct")
    allowed = {row["previous_revenue"], row["current_revenue"], row["mom_pct"], "8"}  # "8" = Part 2 threshold
    untraceable = [n for n in re.findall(r"-?\d+(?:\.\d+)?", message) if n not in allowed]
    if untraceable:
        raise GuardrailError(f"output guardrail: untraceable number(s) {untraceable} in message for {row['category']}")
    if any(w in message.lower() for w in CAUSAL_WORDS):
        raise GuardrailError(f"output guardrail: unsupported causal claim in message for {row['category']}")


def run(month: str, previous_month_csv: str, current_month_csv: str) -> dict:
    """Run subtasks 1-8 for `month` and return the seven-key result dict."""
    # (1) Load the feeds and run validate_feed - the Input guardrail, before anything else.
    errors = []
    for path in (current_month_csv, previous_month_csv):
        ok, errs = validate_feed(path)
        errors += [e for e in errs if e not in errors]
    # (2) If invalid: Hard Stop and report errors. No MoM computation is attempted.
    if errors:
        return _hard_stop(month, errors)

    if month not in CALENDAR_MONTHS or CALENDAR_MONTHS.index(month) == 0:
        return _hard_stop(month, [f"unknown or unsupported run month: {month!r}"])
    prev_month = CALENDAR_MONTHS[CALENDAR_MONTHS.index(month) - 1]
    current = _rows_for(current_month_csv, month)
    previous = _rows_for(previous_month_csv, prev_month)
    if not current:
        return _hard_stop(month, [f"no {month} rows in current-month feed"])
    if not previous:
        return _hard_stop(month, [f"no {prev_month} rows in previous-month feed"])
    missing = [c for c in current if c not in previous]
    if missing:
        return _hard_stop(month, [f"no {prev_month} revenue for category={c}" for c in missing])
    zero = [c for c in current if float(previous[c]) == 0]
    if zero:
        return _hard_stop(month, [f"{prev_month} revenue is zero for category={c}; MoM undefined" for c in zero])

    # (3) Compute mom_growth for every category; (4) run is_flagged on every category.
    rows = []
    for category, cur_rev in current.items():
        pct = mom_growth(float(previous[category]), float(cur_rev))
        rows.append({"previous_month": prev_month, "month": month, "category": category,
                     "previous_revenue": previous[category], "current_revenue": cur_rev,
                     "mom_pct": str(pct), "result": is_flagged(pct, THRESHOLD)})

    # (5) Sort flagged categories by abs(mom_pct) descending (stable: ties keep feed order).
    flagged = sorted((r for r in rows if r["result"] == "flagged"), key=lambda r: -abs(float(r["mom_pct"])))
    # (7b) Exact-boundary categories go to their own list - never flagged, suppressed, or dropped.
    escalated = [r["category"] for r in rows if r["result"] == "escalate_exact_boundary"]

    with open(RESELLERS_CSV, newline="", encoding="utf-8") as f:
        raw_names = [r["reseller_name"] for r in csv.DictReader(f)]

    # (6) Draft a message via Part 3 for at most the top 3 by magnitude, checking each one.
    drafted = []
    try:
        for row in flagged[:DRAFT_CAP]:
            message = generate_narrative(row)
            _check_message(message, row, raw_names)
            drafted.append({"category": row["category"], "mom_pct": float(row["mom_pct"]),
                            "previous_revenue": float(row["previous_revenue"]),
                            "current_revenue": float(row["current_revenue"]),
                            "drafted": True, "message": message})
    except GuardrailError as e:
        return _hard_stop(month, [str(e)])

    # (7) Remaining flagged categories beyond the cap: "suppressed, review manually", no message.
    suppressed = [r["category"] for r in flagged[DRAFT_CAP:]]

    # (8) Emit one structured object. Drafts are held for human approval - never sent.
    return _result(month, "valid", [], drafted, suppressed, escalated, "drafted_and_held_for_approval")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    run_month = args[0]
    prev_csv = args[1] if len(args) > 1 else DEFAULT_FEED
    cur_csv = args[2] if len(args) > 2 else DEFAULT_FEED
    print(json.dumps(run(run_month, prev_csv, cur_csv), indent=2))
