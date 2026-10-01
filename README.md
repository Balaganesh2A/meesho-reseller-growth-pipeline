# Meesho Reseller Growth Pipeline

## Project Overview

This is a small, offline, end-to-end pipeline for monitoring reseller growth. It finds which
categories moved enough to matter, which resellers are inactive, and which regions are
pulling their weight. It then drafts stakeholder updates that a human must approve, and it
never invents a number.

| Part | What it does | Main files |
|---|---|---|
| 1 — SQL Business Query Engine | Generates the seeded dataset and answers five business questions in SQL | `data/generate_dataset.py`, `part1_sql/queries.sql`, `part1_sql/output/*.csv` |
| 2 — Python Guardrail & Growth-Detection Engine | Validates the feed, computes month-on-month (MoM) growth and applies the 8% flag rule | `part2_engine/growth_engine.py` |
| 3 — Reliable AI Narrative & Prompt-Pack Report | Turns verified growth rows into narratives with a deterministic template, plus the prompt pack, report and masking | `part3_narrative/*` |
| 4 — Agentic Workflow Spec + Mock Agent Runner | Ties Parts 1–3 into one guarded run that drafts and holds messages, plus a question-routing agent | `part4_agent/*` |

## Requirements

- **Python 3.** It was verified with Python 3.14. The code uses `tuple[...]` and `list[...]` type hints, so Python 3.9 or newer is needed.
- **pytest** is the only non-standard dependency, and it is needed only to run the tests:

  ```
  python -m pip install pytest
  ```

**No API keys are required.** The project runs locally and offline. Every narrative is produced
by a deterministic template-fill function, and nothing calls a network service or an LLM.

## Project Structure

```
data/
  generate_dataset.py          seeded generator (verbatim from the brief)
  resellers.csv  orders.csv    generated source data (24 resellers, 900 orders)
  meesho_reseller.db           generated SQLite database (resellers, orders)
part1_sql/
  queries.sql                  the five required queries (Q4 includes the COUNT(*) vs COUNT(order_id) check)
  output/                      monthly_category_revenue.csv, region_revenue.csv, top5_resellers.csv,
                               zero_order_resellers.csv, june_delivered_aov.csv
part2_engine/
  growth_engine.py             mom_growth, is_flagged, validate_feed (+ script that writes the MoM table)
  test_growth_engine.py
  fixtures/                    monthly_category_revenue.csv (copy of Part 1 output), corrupted_feed.csv
  output/mom_growth_results.csv
part3_narrative/
  narrative_generator.py       generate_narrative(row) - deterministic template fill
  masking.py                   alias_for, assert_no_raw_names_leak, require_no_raw_names_leak
  prompt_pack.md               Trigger / Inputs / Prompt / Checklist
  narrative_report.md          Ethnic Wear narratives, self-scoring, chart choice, masked top-reseller narrative
  test_narrative_generator.py  test_report_and_masking.py
  fixtures/mom_growth_results.csv   output/narratives.csv
part4_agent/
  agent_spec.md                Goal, Tools, Memory, Planner, Feedback Loop, Guardrails, Stopping Conditions, GWT specs
  mock_agent_runner.py         run(month, previous_month_csv, current_month_csv) -> dict
  agent.py                     question-routing agent over the verified outputs
  test_mock_agent_runner.py    test_agent.py
  fixtures/agent_questions.json
  output/agent_test_results.json   output/final_submission_verification.md
```

## Dataset Generation

```
python data/generate_dataset.py
```

This writes `data/resellers.csv` (24 rows), `data/orders.csv` (900 rows, 300 each for April,
May and June 2026) and `data/meesho_reseller.db`. It prints:

```
Wrote 24 resellers and 900 orders. Zero-order reseller: RS024
```

The script is the brief's generator, copied verbatim. It uses `random.Random(42)`, and its seed,
weights and row counts must not be changed.

## Run Order

Run all commands from the repository root.

> **The committed outputs are the verified submission artifacts.** Re-running a step
> overwrites its outputs. The dataset is deterministic, so the values do not change, but there
> is no need to regenerate anything just to review the project. To check the results, run the
> tests (see *Testing*) or the read-only Part 1 command below.

1. **Generate or verify the dataset:** `python data/generate_dataset.py`. Skip this if `data/` is already present.
2. **Run Part 1 SQL.** `part1_sql/queries.sql` holds the five queries. This read-only command runs them against the database and prints the results:

   ```
   python -c "import sqlite3; c = sqlite3.connect('file:data/meesho_reseller.db?mode=ro', uri=True); [print(r) for s in open('part1_sql/queries.sql', encoding='utf-8').read().split(';') if s.strip() for r in c.execute(s)]"
   ```

   The five CSVs in `part1_sql/output/` hold the results of Q1, Q2, Q3, Q4a and Q5. The Q4b check is printed only, not saved. The repository has no export script for these CSVs; they are committed as verified outputs.
3. **Run the Part 2 growth engine:** `python part2_engine/growth_engine.py`. It reads `part1_sql/output/monthly_category_revenue.csv` and writes `part2_engine/output/mom_growth_results.csv`.
4. **Run the Part 3 narrative generator:** `python part3_narrative/narrative_generator.py`. It reads the Part 2 output and writes `part3_narrative/output/narratives.csv`.
5. **Run the Part 4 mock runner and agent:** `python part4_agent/mock_agent_runner.py May` (see *Part 4 Usage*).

## Parts Connection

- **Part 1:** `data/meesho_reseller.db` → SQL analysis (`queries.sql`) → Part 1 CSV outputs.
- **Part 2:** `part1_sql/output/monthly_category_revenue.csv` → `validate_feed` → `mom_growth` → `is_flagged` → `part2_engine/output/mom_growth_results.csv`. The column names of the Part 1 CSV (`month,category,revenue,n_orders`) are the input contract.
- **Part 3:** Part 2 growth results → `narrative_generator.generate_narrative()` → `part3_narrative/output/narratives.csv`. Reseller references are masked with `masking.alias_for()`.
- **Part 4:** verified outputs from Parts 1–3 → mock runner / routing agent → validated agent responses.
  - **Imports, not copies:** `mock_agent_runner.py` imports Part 2's `validate_feed`, `mom_growth` and `is_flagged` unmodified.
  - **Narratives:** both `mock_agent_runner.py` and `agent.py` reuse Part 3's actual `generate_narrative()` implementation instead of duplicating its template. Tests check this by object identity.

## Workflow-Pattern Mapping

These use the brief's own wording.

- **Part 1 → Part 2 mirrors the "compute real numbers via SQL first, then hand off" order of operations.**
  - Every revenue figure is computed once, in SQL (`queries.sql` → `monthly_category_revenue.csv`).
  - Part 2 only consumes that output. It validates it, then derives MoM growth and the flag from it.
- **Part 4 mirrors an Intake → Summary → Report Draft → Validate reporting flow** (`mock_agent_runner.run`):

  | Stage | What happens |
  |---|---|
  | **Intake** | Load both monthly feeds and run `validate_feed`. Hard stop if either fails. |
  | **Summary** | `mom_growth` and `is_flagged` for every category, then rank flagged categories by `abs(mom_pct)`. |
  | **Report Draft** | Draft at most the top 3 with Part 3's `generate_narrative()`. List the rest as suppressed and exact-boundary cases as escalated. |
  | **Validate** | Output guardrail on every draft: every number must trace to the source, with no causal claims and no raw reseller names. Then emit the seven-key result with `action_taken = "drafted_and_held_for_approval"`, so a human approves before anything is sent. |

## Testing

```
python -m pytest part2_engine
python -m pytest part3_narrative
python -m pytest part4_agent
```

Combined:

```
python -m pytest part2_engine part3_narrative part4_agent
```

The current verified result is **77 passed**: Part 2 has 6, Part 3 has 19, and Part 4 has 52 (28 routing-agent tests and 24 mock-runner tests). The tests only read the committed data and outputs.

## Part 4 Usage

```
python part4_agent/mock_agent_runner.py May
python part4_agent/mock_agent_runner.py June
python part4_agent/mock_agent_runner.py July part1_sql/output/monthly_category_revenue.csv part2_engine/fixtures/corrupted_feed.csv
```

- **What each run prints:** the seven-key JSON result: `run_month`, `validation_status`, `validation_errors`, `flagged_categories`, `suppressed_categories`, `escalated_categories`, `action_taken`.
- **Arguments:** `month [previous_month_csv] [current_month_csv]`. Both CSVs default to `part1_sql/output/monthly_category_revenue.csv`.
- **The third command** is the corrupted-feed scenario, which ends in a `hard_stop`.

```
python part4_agent/agent.py "How did Ethnic Wear change from April to May?"
python part4_agent/agent.py --verify
```

- **A question:** answers one natural-language question from the verified outputs, giving its intent, answer and source.
- **`--verify`:** runs all of `part4_agent/fixtures/agent_questions.json` and rewrites `part4_agent/output/agent_test_results.json`.

## Python Documentation Consulted

The official Python standard-library documentation (docs.python.org) was used as reference for
the modules the project imports:

- `random`: `Random`, `choice`, `choices`, `randint` and `uniform`, used in the dataset generator.
- `sqlite3`: connections, `executemany`, and read-only URI connections.
- `csv`: `DictReader`, `DictWriter` and `writer`.
- `os`: `os.path` and `os.makedirs`.
- `json`: `dump`, `dumps` and `load`.
- `re`: number extraction and keyword matching in the Part 4 guardrails and routing.
- `sys`: `sys.path` and `sys.argv`.

The pytest documentation (docs.pytest.org) was used for the test suite, a third-party tool used only for testing.

## Known Limitations

1. **Keyword routing.** Part 4 routing (`agent.py`) uses deterministic keyword rules, so unusual wording may be rejected as unsupported. The agent never guesses.
2. **No January runs.** The mock runner uses the calendar month immediately before the requested month, so January is not supported.
3. **How `flagged_categories` is filled — review against the instructor's wording.**
   - **Current behaviour:** `flagged_categories` contains only the drafted categories (at most 3, each with `drafted: true` and a `message`). The remaining flagged categories appear only in `suppressed_categories`.
   - **Why:** this satisfies the brief's "exactly 3 entries in `flagged_categories` with `drafted = true`".
   - **The alternative reading:** suppressed categories would also be listed in `flagged_categories`, with `drafted: false`.
4. **Development artifacts.** `__pycache__/` and `.pytest_cache/` don't need to be submitted, and `.gitignore` already excludes them.
