# Narrative Report — Ethnic Wear, April → May → June 2026

**Audience:** regional and category managers.
**Sources:** `part1_sql/output/monthly_category_revenue.csv` (revenue, order counts) and
`part2_engine/output/mom_growth_results.csv` (MoM % and flag result). Each narrative
follows the prompt pack (`prompt_pack.md`): Context → Insight → Implication.

**Labels used**

- **FACT:** stated directly in the source CSVs.
- **HYPOTHESIS:** a possible explanation the data does not confirm.
- **ACTION:** a recommended next step. It is not a claim.

---

## Narrative 1 — Ethnic Wear, April → May (flagged)

### Context

- **FACT:** This compares Ethnic Wear category revenue for May 2026 against April 2026 (adjacent months).
- **FACT:** Revenue is the sum of quantity × unit price across all Ethnic Wear orders in each month, all order statuses included.

### Insight

- **FACT:** Ethnic Wear revenue increased from INR 104520.77 in April to INR 185107.61 in May, a month-on-month change of +77.10% (Part 2 `mom_pct` = 77.1).
- **FACT:** The result is `flagged`: the absolute change is above the 8% threshold.
- **FACT:** Ethnic Wear order count rose from 64 in April to 104 in May.

### Implication

- **HYPOTHESIS:** The jump may be concentrated in a small number of resellers rather than spread across the base. The category totals cannot confirm or rule this out.
- **ACTION:** Before planning June Ethnic Wear stock or targets around the May level, break the 104 May Ethnic Wear orders down by reseller and by region (from `data/orders.csv` joined to `data/resellers.csv`). Check whether the increase is broad-based or comes from a few resellers.

---

## Narrative 2 — Ethnic Wear, May → June (flagged, opposite direction)

### Context

- **FACT:** This compares Ethnic Wear category revenue for June 2026 against May 2026 (adjacent months).
- **FACT:** Revenue is the sum of quantity × unit price across all Ethnic Wear orders in each month, all order statuses included.

### Insight

- **FACT:** Ethnic Wear revenue decreased from INR 185107.61 in May to INR 76371.53 in June, a month-on-month change of -58.74% (Part 2 `mom_pct` = -58.74).
- **FACT:** The result is `flagged`: the absolute change is above the 8% threshold, this time downward.
- **FACT:** Ethnic Wear order count fell from 104 in May to 52 in June.
- **FACT:** June Ethnic Wear revenue (INR 76371.53) is also below the April level (INR 104520.77).

### Implication

- **HYPOTHESIS:** The May peak may have been a one-off rather than a new baseline. The three months of data cannot confirm this, and they contain no information on promotions, pricing or seasonality.
- **ACTION:** Compare the resellers that drove May Ethnic Wear orders with their June orders, reseller by reseller (from `data/orders.csv`). Contact the resellers whose June Ethnic Wear orders dropped the most before reacting at category level.

---

## Self-scoring

Scores are out of 5. The first four rows are the brief's refinement criteria. The last three are the additional review criteria.

### Narrative 1 — April → May

| Criterion | Score | Why |
|---|---|---|
| Specificity | 5/5 | It names the category, both months, both revenue figures, the MoM value and the order counts, each taken from the CSVs. |
| Audience fit | 4/5 | It is written in plain business terms for a manager, though the file paths in the action are more useful to an analyst. |
| Completeness | 5/5 | Context, Insight and Implication are all present. |
| Actionability | 5/5 | The action names one concrete check: break the May orders down by reseller and region, from named files. |
| Factual accuracy | 5/5 | Every figure matches `monthly_category_revenue.csv` and `mom_growth_results.csv` exactly. |
| Hypothesis discipline | 5/5 | The only possible explanation is labelled HYPOTHESIS and stated as unconfirmed, and no FACT contains a cause. |
| Clarity | 5/5 | Each section has a short bullet list with one claim per line. |

### Narrative 2 — May → June

| Criterion | Score | Why |
|---|---|---|
| Specificity | 5/5 | It names the category, both months, both revenue figures, the -58.74% value and the order counts, and it states the direction explicitly. |
| Audience fit | 4/5 | It is manager-focused and recommends contacting resellers, though the file references are analyst-oriented. |
| Completeness | 5/5 | Context, Insight and Implication are all present. |
| Actionability | 5/5 | The action is specific: a reseller-by-reseller May vs. June comparison, then contacting the largest decliners. |
| Factual accuracy | 5/5 | Every figure matches the source CSVs exactly, and the negative sign is kept. |
| Hypothesis discipline | 5/5 | The one-off explanation is labelled HYPOTHESIS, and the narrative says outright that the data has no promotion, pricing or seasonality information. |
| Clarity | 5/5 | The structure is the same as Narrative 1, so the two read side by side. |

---

## Chart-choice justification (text only, no images)

**1. "Which month had the highest total revenue?"** (April INR 419417.43, May INR 444594.25, June INR 398055.24)
Use a **vertical bar chart** with one bar per month, in calendar order. It is a bivariate view: one categorical variable (month) against one measure (total revenue).
- The tallest bar (May) answers the question within 10 seconds.
- The y-axis must start at zero. The three totals are fairly close, and a truncated axis would make the gaps look much larger than they are.
- There is a single series, so no legend is needed.
- Use flat 2D bars, no 3D.

**2. "What percentage share does Ethnic Wear represent of April's total revenue?"** (INR 104520.77 of INR 419417.43 = 24.92%)
Use a **single 100% stacked horizontal bar** for April. It is a univariate composition view: one total split across the five categories.
- Highlight the Ethnic Wear segment and label it with 24.92%, so the share reads within 10 seconds. Grey out the other segments with direct labels.
- The axis runs from 0% to 100%.
- Direct labels replace a legend.
- No 3D or exploded pie, which distorts how big each slice looks.

**3. "How do the four regions compare on total revenue?"** (North INR 337125.46, West INR 333106.33, South INR 316736.68, East INR 275098.45)
Use a **horizontal bar chart sorted from highest to lowest**. It is a bivariate view: region against revenue.
- Sorting puts the ranking (North first, East last) in reading order, so it is clear within 10 seconds.
- The axis starts at zero, because North and West differ only slightly and a cut axis would exaggerate it.
- One series, so no legend. Flat 2D bars, no 3D.

**4. Showing the Ethnic Wear trend (April → May → June).**
Use a **line chart with markers** for the three monthly Ethnic Wear revenues (104520.77, 185107.61, 76371.53).
- The rise then fall is visible within 10 seconds, and each point can carry its MoM label (+77.10%, -58.74%).
- The y-axis starts at zero, so the size of the drop below April's level isn't exaggerated.
- With Ethnic Wear alone there is one series and no legend.
- To compare all five categories over the three months, the view becomes multivariate (month × category × revenue). Use one line per category, and add a legend, or better, direct end-of-line labels, because there are now multiple series.

---

## Top-reseller narrative (masked)

- **FACT:** Five resellers had total spend above INR 50000 across April–June 2026 (Part 1, `HAVING total_spend > 50000`).
- **FACT:** Ranked by total spend:
  1. ALIAS-19 (West): INR 75295.09
  2. ALIAS-22 (West): INR 73882.33
  3. ALIAS-12 (South): INR 69936.46
  4. ALIAS-06 (North): INR 64238.97
  5. ALIAS-05 (North): INR 61825.02
- **FACT:** Two of the top five are in the West region and two are in the North.
- **ACTION:** Review account coverage for these five resellers first, using the alias-to-ID mapping held internally.

Resellers are referenced only by region and `alias_for(reseller_id)`, never by raw name.
`masking.assert_no_raw_names_leak(<this report>, <all 24 reseller names>)` returns `True`,
which `test_report_and_masking.py` checks.
