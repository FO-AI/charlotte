# Outside scholarships: quantifying time and dollar savings

**Issue:** [#58 — Proposal for time and dollars saved on rows that do not need review](https://github.com/FO-AI/charlotte/issues/58)  
**Status:** Proposal only — no implementation until Om agrees  
**Audience:** Engineering + leadership (dollar impact, not models / LOC)  
**Related but separate:** [#17](https://github.com/FO-AI/charlotte/issues/17) pipeline wall-clock speed

---

## Why this exists

Leadership does not care which vision model we used or how many lines of code changed. They understand **dollars**.

Om’s framing (Teams, 2026-10-19):

> For each row the system correctly extraction i.e. it was not flagged for review, tie that to time saved and multiply by $X and aggregate to prove the utility.

Same pattern as the cashiers **email agent**: count items the system finished → multiply by minutes a person would have spent → multiply by a basic UNC hourly wage.

This document is the written proposal Om asked for **before any code**.

---

## One-sentence goal

After each outside-scholarship batch, report **how many Excel rows Charlotte accepted without human review**, convert that into **minutes saved**, then into **dollars saved**, using measurable assumptions—not invented ones.

---

## Core equation

```
dollars_saved =
  (rows_not_flagged_for_review)
  × (minutes_per_manual_row)
  ÷ 60
  × (hourly_wage_usd)
```

Also report the intermediates:

| Output | Formula |
| --- | --- |
| Rows counted | Rows that never needed review (see below) |
| Minutes saved | `rows_counted × minutes_per_manual_row` |
| Dollars saved | `minutes_saved / 60 × hourly_wage_usd` |

### Email-agent analogy (worked the same way)

| Email agent | Outside scholarships |
| --- | --- |
| Emails categorized / handled as “AI agent” | Excel PID-rows that never hit Needs review |
| Avg minutes for an employee to answer one email | Avg minutes to read one check and enter one Excel row |
| Basic UNC hourly wage | Same idea (admin band floor until Derek names the real job) |

---

## What counts as a “saved” row

**Count only rows the system accepted on its own.**

A check (and every Excel row it expands into) does **not** count if it was ever in Needs review for any current flag, including:

| Flag / condition | Why it doesn’t count |
| --- | --- |
| Missing required fields | Person must fill |
| Bad / missing PID, No AD match, AD unreachable | Person must fix / decide |
| Multiple PIDs | Person must Mark verified (#34) |
| Amount not split | Person must resolve or verify (#44/#56) |
| Name mismatch (payee vs AD) | Person must correct (#34) |
| Supporting looks like check | Person must confirm grouping (#55) |
| Extraction failed | Person must enter values (#55) |

**Proposal default:** only rows that were **never flagged** count.  
A row that was flagged, then edited and Mark verified, still took human time → **does not count** (open decision below).

**Unit:** one Excel export row (one PID line), not one PDF page and not one uploaded file. Multi-PID checks that auto-OK with a complete amount split can contribute multiple rows; multi-PID that still need Mark verified contribute zero until/unless we change the rule.

---

## Minutes per row (must come from real people)

Do **not** invent this number. Om’s method:

1. Ask **Derek** (or whoever enters checks by hand) to time **a couple of real runs**.
2. Record total minutes: reading checks + entering rows in Excel (same work Charlotte replaces when a row is clean).
3. Divide by the number of rows in that run → **minutes per row**.

```
minutes_per_manual_row = total_minutes_for_run / row_count_in_run
```

Use the average across a few runs if they vary. Put the raw timings in the issue or an appendix when collected.

### What to ask Derek (short script)

- Who usually enters outside-scholarship checks into the template?
- For a typical batch (or the Derek supporting-docs PDF), how long from “PDF in hand” to “rows in Excel,” including reading supporting pages?
- How many rows did that batch produce?
- Any steps Charlotte already skips for them (AD lookup, term mapping, etc.) that should stay inside that timing?

Until those timings exist: **show row count only; leave minutes and dollars blank.** Do not ship a fake minutes-per-row.

---

## Hourly wage (starting assumption)

**Starting figure** until Derek names the real classification:

| Source | Value |
| --- | --- |
| UNC SHRA Career Banding Salary Ranges (April 2026) | Administrative Support Associate band **minimum** $33,540 / year |
| Hours/year | 2,080 |
| Hourly | **$16.13 / hour** |

Link: [SHRA career banding salary ranges (PDF)](https://hr.unc.edu/wp-content/uploads/sites/1483/2026/04/shra-career-banding-salary-ranges.pdf)

Replace this if the people who enter checks sit in a higher band (or student wage, etc.). The equation stays the same; only the rate changes.

---

## Worked example (illustrative only)

Numbers below are **placeholders** so leadership can see the shape. Replace with Derek’s minutes and the agreed wage before publishing as “impact.”

| Input | Example |
| --- | --- |
| Rows not flagged | 40 |
| Minutes per manual row | 3.0 (placeholder) |
| Hourly wage | $16.13 |

```
minutes_saved = 40 × 3.0 = 120 minutes (2.0 hours)
dollars_saved = 2.0 × 16.13 ≈ $32.26 for that batch
```

Monthly / semester rollup = sum of batch `dollars_saved` (and separately sum of rows / minutes).

---

## What to show in the product (after agreement)

After a batch is extracted (and again on Excel export), surface three numbers:

1. **Rows counted** (never-flagged rows)  
2. **Minutes saved** (blank until minutes/row is set)  
3. **Dollars saved** (blank until minutes/row and wage are set)

| Until timed runs exist | After assumptions locked |
| --- | --- |
| Rows only | All three |
| No invented minutes/$ | Same formula everywhere (review UI + Excel) |

Placement sketch (implementation detail later):

- Review screen: small summary next to the existing “N of M left · PIDs · $total” strip  
- Excel: a short “Impact” block above or below the review table (rows / minutes / dollars + footnote of wage and minutes/row used)

---

## Open decisions (need Om / Derek)

| # | Decision | Proposal default |
| --- | --- | --- |
| 1 | Minutes per row | From Derek’s timed runs only |
| 2 | Wage / job class | $16.13 ASA minimum until named otherwise |
| 3 | Flagged → Verified rows | **Do not count** (human still spent time) |
| 4 | Multi-PID complete split, still Needs review for Multiple PIDs | **Do not count** until verified? Or count after verify? Default: never-flagged only → multi-PID never auto-counts |
| 5 | Aggregate period | Per batch now; month/semester rollup later if useful |

Decision 4 matters: today Multiple PIDs always Needs review, so **zero multi-PID rows would count** under the strict “never flagged” rule even when the amount split is perfect. If leadership wants credit for “split was right, human only clicked Verify,” we need an explicit rule change.

---

## How this relates to other work

| Work | Relationship |
| --- | --- |
| **#58 (this)** | Dollar / time **impact** of clean rows |
| **#17** | Make the **machine** faster (upload → preview). Does not by itself prove $ to leadership |
| **#18** | Payment Validation VLOOKUP in Excel — export correctness, not impact math |
| **#55 / #56** | More fields / splits → more flags possible → can **lower** “rows counted” if more checks need review. That’s honest: impact tracks automation that sticks without a person |

Faster pipeline (#17) and higher clean-row rate (#58) both help the story; they answer different questions:

- #17: “How long until the cashier sees the review UI?”  
- #58: “How much human Excel work did we avoid?”

---

## Implementation outline (after sign-off only)

No code until Om says the approach is good.

1. Define a pure function: given reviewed checks + current flag rules → `rows_counted`.  
2. Config or env for `minutes_per_manual_row` and `hourly_wage_usd` (blank / null = hide $ and minutes).  
3. Preview API + review UI summary.  
4. Excel export block + footnote (assumptions).  
5. Tests: flagged vs clean rows; multi-PID; incomplete split; blank assumptions hide $.  
6. Optional: log batch totals for semester rollups (no PII beyond what’s already in export).

**Out of scope for #58**

- Second name lookup / PaymentValidation server read (#18).  
- Changing which rows are flagged.  
- Pipeline latency work (#17).

---

## Research / data checklist

- [ ] Timed manual runs with Derek (total minutes, row counts → minutes/row)  
- [ ] Confirm job classification / wage with Derek or Om  
- [ ] Confirm decision on Mark verified after flag  
- [ ] Confirm multi-PID “verify only” counting rule  
- [ ] Om sign-off on this proposal  
- [ ] Then implement and show numbers on a real batch  

---

## Summary for leadership

Charlotte already decides which check rows are clean enough to export without review. We count those rows, multiply by how long a person would have spent entering one row, and multiply by a published UNC admin hourly rate. That is the dollar impact. We will not invent the minutes-per-row number—cashiers who do the work will time it—and we will not count rows a person still had to touch.
