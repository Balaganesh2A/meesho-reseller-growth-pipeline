# Prompt Pack — Flagged Category Stakeholder Update

Reusable prompt for turning one row of Part 2's verified output into a
stakeholder update for a regional / category manager.

Source data: `part2_engine/output/mom_growth_results.csv`
(columns `previous_month, month, category, previous_revenue, current_revenue, mom_pct, result`).

The pipeline runs fully offline. `part3_narrative/narrative_generator.py` fills these
placeholders deterministically from the CSV (`generate_narrative(row)`), with no
LLM and no API key. The prompt below is the specification that the template
follows, and it is also what an optional LLM would receive, word for word.

---

# Trigger

Run this prompt for a row of `mom_growth_results.csv` when its `result` is `"flagged"`,
i.e. `is_flagged(mom_pct)` from Part 2 returned `"flagged"` because `abs(mom_pct) > 8.0`.

- `not_flagged` rows do not trigger a stakeholder update.
- `escalate_exact_boundary` rows do not trigger an update either. They go to a human for review.
- Part 4 caps drafting at the top 3 flagged rows by `abs(mom_pct)`.

# Inputs

Input list. Every placeholder comes straight from one CSV row (or is derived from its sign).
No other value may appear in the output.

| Placeholder | Source | Example (April → May, Ethnic Wear) |
|---|---|---|
| `{prev_month}` | `previous_month` column | April |
| `{month}` | `month` column | May |
| `{category}` | `category` column | Ethnic Wear |
| `{previous_revenue}` | `previous_revenue` column, copied verbatim | 104520.77 |
| `{current_revenue}` | `current_revenue` column, copied verbatim | 185107.61 |
| `{mom_pct}` | `mom_pct` column, copied verbatim with its sign | 77.1 |
| `{result}` | `result` column | flagged |
| `{direction}` | sign of `mom_pct`: `increased` if > 0, `decreased` if < 0, `unchanged` if 0 | increased |

The comparison is always between adjacent months only (`{prev_month}` → `{month}`).

# Prompt

```text
You are writing a short monthly update for a Meesho regional / category manager.
Use ONLY the values below. Do not compute, round, or introduce any other number.

  Comparison:        {prev_month} -> {month}
  Category:          {category}
  Previous revenue:  INR {previous_revenue} ({prev_month})
  Current revenue:   INR {current_revenue} ({month})
  MoM change:        {mom_pct}%
  Direction:         revenue {direction}
  Threshold result:  {result} (threshold = 8% absolute MoM change)

Write exactly three labelled parts:

1. CONTEXT - say what is measured ({category} revenue) and over which period
   ({prev_month} vs. {month}). Label each statement FACT.

2. INSIGHT - state that revenue {direction} from INR {previous_revenue} to
   INR {current_revenue}, a MoM change of {mom_pct}%, and that the result is
   {result}. Label it FACT.

3. IMPLICATION - give one concrete, checkable next step (name what to check
   and where), not a vague "look into it". If you suggest any possible reason
   for the change, label it HYPOTHESIS and say the data does not confirm it.

Rules:
- FACT statements may contain only the supplied values and what follows from them directly.
- Never present a cause (seasonality, promotions, pricing, demand, competition, etc.)
  as a FACT. The data contains no cause information.
- Never state a number that is not one of the supplied placeholder values.
- Refer to resellers only by coded alias (e.g. ALIAS-19), never by raw name.
- Plain business language for a manager, not a data engineer.
```

# Checklist

Run every check on the draft before it is used. Any failure blocks the draft.

1. **Exact month pair.** The draft names `{prev_month}` → `{month}`, and they match the CSV row (adjacent months only).
2. **Category.** The draft names `{category}` exactly as in the CSV.
3. **Numbers trace to placeholders.** Every number in the draft exactly matches `{previous_revenue}`, `{current_revenue}`, `{mom_pct}` or the 8% threshold. No other figure appears.
4. **Sign and direction.** The sign of the MoM value is kept as supplied, and the stated direction (`increased`/`decreased`) agrees with it.
5. **Result.** The draft states `{result}` exactly as in the CSV (`flagged`).
6. **Structure.** Context, Insight and Implication are all present, in that order.
7. **FACT vs. HYPOTHESIS.** Every claim is labelled FACT or HYPOTHESIS, and FACT statements contain no causal words ("because", "due to", "caused by", "driven by").
8. **No invented causes or unsupported claims.** Any suggested reason is labelled HYPOTHESIS and explicitly marked as unconfirmed by the data.
9. **Actionable.** The implication names a specific check or action (what, and where to look), not "look into {category}".
10. **Masking.** No raw reseller name appears. Resellers are referenced only as `alias_for(reseller_id)` plus region, and `masking.assert_no_raw_names_leak(draft, reseller_names)` returns `True`.
