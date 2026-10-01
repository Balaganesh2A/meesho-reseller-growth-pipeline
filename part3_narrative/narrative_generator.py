"""Part 3 - Deterministic narrative generator (offline template fill, no LLM/API).

Input:  part2_engine/output/mom_growth_results.csv
        previous_month,month,category,previous_revenue,current_revenue,mom_pct,result

Output: part3_narrative/output/narratives.csv
        One row per input row, in the same order, with these columns:

        previous_month    prior month of the comparison (copied from input)
        month             current month of the comparison (copied from input)
        category          product category (copied from input)
        previous_revenue  INR revenue in previous_month (copied verbatim from input)
        current_revenue   INR revenue in month (copied verbatim from input)
        mom_pct           month-on-month % change (copied verbatim, sign preserved)
        result            flagged | not_flagged | escalate_exact_boundary (copied from input)
        direction         increased | decreased | unchanged (derived from the sign of mom_pct)
        narrative         the stakeholder-ready sentence built from the fields above

Every figure in a narrative is the exact input string for that row, so no
number is ever recomputed, reformatted, or invented.
"""

import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
DEFAULT_INPUT = os.path.join(PROJECT_ROOT, "part2_engine", "output", "mom_growth_results.csv")
DEFAULT_OUTPUT = os.path.join(HERE, "output", "narratives.csv")

INPUT_COLUMNS = ["previous_month", "month", "category", "previous_revenue",
                 "current_revenue", "mom_pct", "result"]
OUTPUT_COLUMNS = INPUT_COLUMNS + ["direction", "narrative"]

RESULT_SENTENCES = {
    "flagged": "Result: flagged - the change is beyond the 8% threshold and needs attention.",
    "not_flagged": "Result: not_flagged - the change is within the 8% threshold; no action needed.",
    "escalate_exact_boundary": ("Result: escalate_exact_boundary - the change sits exactly on the 8% "
                                "threshold and is held for human review."),
}


def direction_of(mom_pct: str) -> str:
    value = float(mom_pct)
    if value > 0:
        return "increased"
    if value < 0:
        return "decreased"
    return "unchanged"


def generate_narrative(row: dict) -> str:
    """Fill the narrative template for one Part 2 result row."""
    result = row["result"]
    if result not in RESULT_SENTENCES:
        raise ValueError(f"unknown result {result!r} for category={row['category']}")
    direction = direction_of(row["mom_pct"])
    if direction == "unchanged":
        movement = f"was unchanged at INR {row['current_revenue']}"
    else:
        movement = (f"{direction} from INR {row['previous_revenue']} "
                    f"to INR {row['current_revenue']}")
    return (f"{row['previous_month']} -> {row['month']}: {row['category']} revenue {movement}, "
            f"a month-on-month change of {row['mom_pct']}%. {RESULT_SENTENCES[result]}")


def build_narratives(csv_path: str) -> list[dict]:
    """Read the Part 2 CSV and return one output row per input row, order preserved."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != INPUT_COLUMNS:
            raise ValueError(f"unexpected input columns: {reader.fieldnames}")
        out = []
        for row in reader:
            record = {col: row[col] for col in INPUT_COLUMNS}
            record["direction"] = direction_of(row["mom_pct"])
            record["narrative"] = generate_narrative(row)
            out.append(record)
    return out


def write_narratives(rows: list[dict], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    rows = build_narratives(DEFAULT_INPUT)
    write_narratives(rows, DEFAULT_OUTPUT)
    for r in rows:
        print(r["narrative"])
    print(f"Wrote {len(rows)} narratives to {DEFAULT_OUTPUT}")
