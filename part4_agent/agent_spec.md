# Agent Specification — Category Growth Monitoring Agent

This document describes the agent as implemented in `part4_agent/mock_agent_runner.py`,
with entry point `run(month, previous_month_csv, current_month_csv) -> dict`.
It runs fully offline: no network call, no API key, and no message-sending integration.

A separate question-answering front end, `part4_agent/agent.py`, routes natural-language
questions to the same verified outputs. It is described at the end under
*Related component*. It is not part of the graded runner contract.

---

# Goal

Keep Meesho category managers informed of any category whose month-on-month revenue
moves beyond the 8% threshold, with a human approving every message before it goes out.

Concretely: given monthly category revenue data, identify the categories whose change
is meaningful (Part 2's rule). Draft a controlled, traceable message for the largest
movers using Part 3's template, and hold every draft for approval.

# Tools

These are the only tools the runner calls. All of them exist in this repository, and
the runner imports them without modification.

| Tool | Location | Used for |
|---|---|---|
| Monthly category revenue feed | `part1_sql/output/monthly_category_revenue.csv` (Part 1 SQL output, columns `month,category,revenue,n_orders`) | Input data for both months. It is the default `previous_month_csv` / `current_month_csv`. |
| `validate_feed(csv_path)` | `part2_engine/growth_engine.py` | Input guardrail: missing category, missing / non-numeric / negative revenue. |
| `mom_growth(previous, current)` | `part2_engine/growth_engine.py` | `round((current - previous) / previous * 100, 2)` per category. |
| `is_flagged(mom_pct, threshold=8.0)` | `part2_engine/growth_engine.py` | Classifies each change as `flagged`, `not_flagged` or `escalate_exact_boundary`. |
| `generate_narrative(row)` | `part3_narrative/narrative_generator.py` | Prompt-pack template fill for each drafted message. It is called with the verified row, and its output is used unchanged. |
| `require_no_raw_names_leak(text, names)` | `part3_narrative/masking.py` | Output check that no raw reseller name appears in a message. Raw names are read, read-only, from `data/resellers.csv`. |

The verified Part 2 output `part2_engine/output/mom_growth_results.csv` is not read by
the runner. The runner recomputes the same values with the same Part 2 functions, and
the tests check that its output equals that file.

# Memory

The agent keeps no memory between runs and no persistent business knowledge.

- **Between runs:** the "previous month's revenue per category" that the next MoM needs is
  not stored by the agent. It is supplied explicitly on every run as `previous_month_csv`,
  so each run is reproducible from its inputs alone.
- **Within a run:** it holds only the following, all of which trace to the two supplied CSVs:
  - the previous month's name, which is the calendar month before `month`
  - per category, the previous and current revenue (verbatim strings from the feeds)
  - the `mom_pct` and flag result computed from those revenues
  - the ranked flagged list
  - the drafted messages
- **Never held:** no historical facts, causes or external data are introduced.

# Planner

These are the ordered subtasks, executed in this order by `run()` every time. Given the
same inputs, the output is identical.

1. **Load and validate.** Run `validate_feed` on the current-month feed and the previous-month feed.
2. **Hard stop if invalid.** If any validation error exists, return immediately with
   `validation_status = "invalid"`, the errors, and `action_taken = "hard_stop"`.
   - The same hard stop applies if:
     - the run month is unknown
     - either feed has no rows for its month
     - a category has no previous-month revenue
     - a previous revenue is zero, so the MoM is undefined
   - No MoM computation, ranking or drafting happens.
3. **Compute growth.** For every category in the current month, call
   `mom_growth(previous_revenue, current_revenue)`. The previous month is the calendar
   month before `month`, e.g. April for May. Only adjacent months are compared.
4. **Flag.** Run `is_flagged(mom_pct)` (threshold 8.0) on every category.
5. **Rank.** Sort the `flagged` categories by `abs(mom_pct)` descending. Ties keep feed order, because the sort is stable.
6. **Draft at most the top 3.** For the top 3 ranked categories, call Part 3's
   `generate_narrative(row)` and check the message (see *Feedback Loop*). The cap exists
   to prevent notification flooding, i.e. drafting one message per flagged item with no limit.
7. **Suppress the rest.** Flagged categories beyond the cap are listed by name in
   `suppressed_categories` ("suppressed, review manually"). No message is drafted for them.
   - **7b. Escalate exact-boundary categories.** Any category whose result is `escalate_exact_boundary`
   goes into `escalated_categories`. It is never drafted, and never placed in the flagged
   or suppressed lists.
   - Categories that are `not_flagged` appear in none of the three lists.
8. **Emit one structured object** with exactly the seven keys below, with
   `action_taken = "drafted_and_held_for_approval"`.

**Output schema** (assignment section 4.3). These are the only top-level keys:

| Key | Type | Meaning |
|---|---|---|
| `run_month` | str | The month passed to `run()`. |
| `validation_status` | `"valid"` / `"invalid"` | Whether the run passed all checks. |
| `validation_errors` | list[str] | Empty on success. On a hard stop, the exact errors. |
| `flagged_categories` | list[object] | The drafted categories, in rank order. Each has `category`, `mom_pct`, `previous_revenue`, `current_revenue`, `drafted` (true) and `message`. |
| `suppressed_categories` | list[str] | Flagged categories beyond the top-3 cap, in rank order. |
| `escalated_categories` | list[str] | Exact-boundary (8.0%) categories. |
| `action_taken` | `"drafted_and_held_for_approval"` / `"hard_stop"` | The run outcome. |

**Interpretation note.** The brief requires "exactly 3 entries in `flagged_categories`
with `drafted = true`" and a separate `suppressed_categories` list of names. This
implementation therefore puts only the drafted categories in `flagged_categories`, with
`drafted` always `true`. Suppressed categories appear only in `suppressed_categories`.

# Feedback Loop

**Human approval (the required feedback loop).** No drafted message is ever considered
"sent". Every successful run ends with `action_taken = "drafted_and_held_for_approval"`.
- A human reviews the held drafts and also the suppressed and escalated lists.
- That review is the only path to sending.
- Approval is simulated by this flag. There is no Gmail or SMTP integration.

**Validation after each step.** If any check fails, the run hard-stops instead of continuing:

| Step | Check | On failure |
|---|---|---|
| Feed | `validate_feed` on both CSVs | Hard stop with the exact error strings. |
| Calculation inputs | Both months present, every category has a previous value, and no previous value is zero | Hard stop. |
| Calculation | MoM comes only from `mom_growth`, and the flag only from `is_flagged` | Covered by tests: the result must equal `part2_engine/output/mom_growth_results.csv`. |
| Ranking | Only `flagged` rows are ranked, by `abs(mom_pct)` descending, with at most 3 drafted | Covered by tests: order and cap. |
| Narrative | Each message contains its category and exact `mom_pct`. Every number in it is that row's previous revenue, current revenue, `mom_pct`, or the 8% threshold. It has no causal wording and no raw reseller name. | Hard stop with an `output guardrail: ...` error. No partial drafts are returned. |
| Output | The result has exactly the seven keys, and `action_taken` is one of the two values | Checked inside `_result()` and in the tests. |

# Guardrails

These are the three guardrails required by the assignment:

1. **Input guardrail.** `validate_feed` must pass before anything else runs.
   - Covers both feeds: missing category, missing revenue, non-numeric revenue, negative revenue.
   - A failure is a Hard Stop, not a silent skip.
2. **Action guardrail.** No message is ever auto-sent, only drafted and held.
   - The runner has no send capability at all.
   - At most 3 messages are drafted per run.
3. **Output guardrail.** Every number in a drafted message must trace back to a Part 1 or Part 2 value. No invented figures.
   - Enforced on every message before it is returned.

These implementation checks also run under the output guardrail. They are not separate assignment requirements:
- no causal claim (e.g. promotion, pricing, demand, seasonality) appears in a message
- no raw reseller name appears (Part 3 masking)

# Stopping Conditions

**Success:**
- The run completes with `validation_status = "valid"` and `action_taken = "drafted_and_held_for_approval"`.
- Every drafted number is traceable.
- Zero drafts is a correct success when nothing crossed the threshold.

**Error (Hard Stop).** The run returns immediately with `validation_status = "invalid"`,
the errors surfaced in `validation_errors`, all three category lists empty, and
`action_taken = "hard_stop"`. It never produces a partial result. The triggers are:
- `validate_feed` returns `False` for either feed, i.e. any of these:
  - a missing required column
  - a missing category
  - a missing revenue
  - a non-numeric revenue
  - a negative revenue
- an unknown or unsupported run month
- no rows for the run month, or for the previous month, which is insufficient data for the comparison
- a category with no previous-month revenue, or a previous revenue of zero
- an output-guardrail failure on any drafted message

# Given-When-Then Specifications

**Agent-level versions of Part 2's four required tests:**

1. **GIVEN** April→May Ethnic Wear revenue moves from 104520.77 to 185107.61, **WHEN** the agent runs for May,
   **THEN** Ethnic Wear's `mom_pct` is 77.1, it is flagged, and it is drafted first.
2. **GIVEN** May→June Beauty & Personal Care revenue moves from 35542.11 to 37559.07, **WHEN** the agent
   runs for June, **THEN** its `mom_pct` is 5.67, it is `not_flagged`, and it appears in neither
   `flagged_categories` nor `suppressed_categories`.
3. **GIVEN** a synthetic pair previous=100000, current=108000, so the growth is exactly on the threshold boundary,
   **WHEN** the agent runs, **THEN** `mom_pct` is exactly 8.0, and the category is listed in
   `escalated_categories`, not in `flagged_categories` and not in `suppressed_categories`.
4. **GIVEN** the corrupted feed `part2_engine/fixtures/corrupted_feed.csv` as the current-month feed,
   **WHEN** the agent runs, **THEN** it returns `validation_status = "invalid"` and `action_taken = "hard_stop"`,
   with exactly 3 errors in order: the negative-revenue row, the missing-category row, then the missing-revenue row.

**Runner scenarios:**

5. **Valid May data.** **GIVEN** the verified Part 1 feed for April and May, **WHEN** `run("May", feed, feed)`,
   **THEN** `validation_status = "valid"` and the drafted entries are, in order, Ethnic Wear (77.1),
   Western Wear (-23.6) and Kids Wear (-23.48). `suppressed_categories` holds Beauty & Personal Care
   and Home & Kitchen, `escalated_categories` is empty, and
   `action_taken = "drafted_and_held_for_approval"`.
6. **Valid June data.** **GIVEN** the verified feed for May and June, **WHEN** `run("June", feed, feed)`,
   **THEN** the drafted entries are, in order, Ethnic Wear (-58.74), Home & Kitchen (42.59) and
   Kids Wear (23.9). `suppressed_categories` is exactly Western Wear (11.97), and Beauty &
   Personal Care (5.67) appears in neither list.
7. **Corrupted feed.** **GIVEN** the corrupted fixture, **WHEN** the agent runs, **THEN** it
   hard-stops with exactly the three error strings below. It computes no MoM, and
   `flagged_categories`, `suppressed_categories` and `escalated_categories` are all empty.
   - `"line 3: negative revenue (-4200.0) for category=Western Wear"`
   - `"line 4: missing category (month=July)"`
   - `"line 6: missing revenue (category=Home & Kitchen)"`
8. **Top-3 selection.** **GIVEN** five flagged categories, **WHEN** the agent runs, **THEN** exactly
   the three with the largest `abs(mom_pct)` are drafted, in descending order of magnitude.
9. **Suppression beyond top 3.** **GIVEN** more than three flagged categories, **WHEN** the agent runs,
   **THEN** every flagged category beyond the third is in `suppressed_categories`, with no message.
   Fewer than three flagged categories means nothing is suppressed.
10. **Numerical traceability.** **GIVEN** any successful run, **WHEN** a drafted entry is inspected,
    **THEN** its `previous_revenue` and `current_revenue` equal the feed values, and its `mom_pct`
    equals `part2_engine/output/mom_growth_results.csv`. Every number in its `message` is one of
    those values or the 8% threshold.
11. **Narrative generation.** **GIVEN** a drafted category, **WHEN** its message is produced, **THEN** it
    is exactly `generate_narrative(row)` from Part 3, called with that category's verified row.
12. **Guardrail failure.** **GIVEN** a drafted message that contains an invented number, a causal
    claim or a raw reseller name, **WHEN** the output guardrail runs, **THEN** the run hard-stops
    with an `output guardrail: ...` error and returns no drafts.

---

## Related component — question-routing agent (`agent.py`)

`part4_agent/agent.py` answers natural-language questions by routing each one to a single
verified output. The six intents are:
- monthly category revenue
- region revenue
- top resellers
- zero-order resellers
- June delivered AOV
- MoM growth

For growth questions it also uses Part 3's `generate_narrative`. It applies the same
principles: it uses only verified values, rejects unknown categories, months and regions,
labels FACT and HYPOTHESIS separately, and masks reseller names. Its tests are in
`part4_agent/test_agent.py`. It is a convenience front end and does not replace `run()`.
