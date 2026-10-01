"""Part 2 - Python Guardrail & Growth-Detection Engine.

Core functions (reused unmodified by Part 4):
    mom_growth(previous, current)       -> float
    is_flagged(mom_pct, threshold=8.0)  -> "flagged" | "not_flagged" | "escalate_exact_boundary"
    validate_feed(csv_path)             -> (bool, list[str])

Running this module as a script reads Part 1's verified output
(part1_sql/output/monthly_category_revenue.csv), validates it, computes
consecutive month-on-month growth per category, and writes
part2_engine/output/mom_growth_results.csv.
"""

import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
DEFAULT_INPUT = os.path.join(PROJECT_ROOT, "part1_sql", "output", "monthly_category_revenue.csv")
DEFAULT_OUTPUT = os.path.join(HERE, "output", "mom_growth_results.csv")

OUTPUT_COLUMNS = ["previous_month", "month", "category", "previous_revenue",
                  "current_revenue", "mom_pct", "result"]


def mom_growth(previous: float, current: float) -> float:
    """Month-on-Month growth percentage, rounded to 2 decimals."""
    return round((current - previous) / previous * 100, 2)


def is_flagged(mom_pct: float, threshold: float = 8.0) -> str:
    """Classify a MoM % against the threshold.

    Never returns a bare boolean: a value exactly on the threshold is held
    for human review instead of being auto-decided either way.
    """
    magnitude = abs(mom_pct)
    if magnitude > threshold:
        return "flagged"
    if magnitude < threshold:
        return "not_flagged"
    return "escalate_exact_boundary"


def validate_feed(csv_path: str) -> tuple[bool, list[str]]:
    """Input guardrail over a month,category,revenue,n_orders CSV.

    Line numbers are 1-indexed with the header as line 1. Errors are reported
    in the order rows are encountered; nothing is fixed or skipped silently.
    """
    errors = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"month", "category", "revenue", "n_orders"}
        missing_cols = required - set(reader.fieldnames or [])
        if missing_cols:
            return False, [f"missing required columns: {sorted(missing_cols)}"]

        for line_no, row in enumerate(reader, start=2):
            month = (row["month"] or "").strip()
            category = (row["category"] or "").strip()
            revenue = (row["revenue"] or "").strip()

            if not category:
                errors.append(f"line {line_no}: missing category (month={month})")
            if not revenue:
                errors.append(f"line {line_no}: missing revenue (category={category})")
                continue
            try:
                value = float(revenue)
            except ValueError:
                errors.append(f"line {line_no}: revenue not numeric: {revenue!r}")
                continue
            if value < 0:
                errors.append(f"line {line_no}: negative revenue ({value}) for category={category}")

    return (len(errors) == 0, errors)


def load_feed(csv_path: str) -> tuple[list[str], list[str], dict]:
    """Read a validated feed.

    Returns months and categories in the order they first appear in the file,
    plus a {(month, category): revenue} lookup.
    """
    months, categories, revenue = [], [], {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["month"] not in months:
                months.append(row["month"])
            if row["category"] not in categories:
                categories.append(row["category"])
            revenue[(row["month"], row["category"])] = float(row["revenue"])
    return months, categories, revenue


def compute_mom_table(csv_path: str, threshold: float = 8.0) -> list[dict]:
    """Validate the feed, then compute MoM for each consecutive month pair.

    Only adjacent months are compared (April->May, May->June), never April->June.
    Raises ValueError if the feed fails validation.
    """
    valid, errors = validate_feed(csv_path)
    if not valid:
        raise ValueError("feed failed validation: " + "; ".join(errors))

    months, categories, revenue = load_feed(csv_path)
    rows = []
    for prev_month, month in zip(months, months[1:]):
        for category in categories:
            previous = revenue[(prev_month, category)]
            current = revenue[(month, category)]
            pct = mom_growth(previous, current)
            rows.append({
                "previous_month": prev_month,
                "month": month,
                "category": category,
                "previous_revenue": previous,
                "current_revenue": current,
                "mom_pct": pct,
                "result": is_flagged(pct, threshold),
            })
    return rows


def write_mom_table(rows: list[dict], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    table = compute_mom_table(DEFAULT_INPUT)
    write_mom_table(table, DEFAULT_OUTPUT)
    for r in table:
        print(f"{r['previous_month']:>5} -> {r['month']:<5} {r['category']:<24} "
              f"{r['mom_pct']:>8}%  {r['result']}")
    print(f"Wrote {len(table)} rows to {DEFAULT_OUTPUT}")
