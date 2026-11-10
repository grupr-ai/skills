# Report rules

`scripts/spend_report.py report` applies these exactly. Follow them by hand
only if the script cannot run.

## Numbers

- Money: US dollars, two decimals, thousands separators (`$6,184.37`). An
  amount above zero but under half a cent prints as `<$0.01`.
- Tokens: `987`, `12.3K`, `412.6M`, `2.5B`. Calls: whole numbers with
  separators.
- Shares are whole percentages of total spend in the window. When there is
  nothing to divide by, print `n/a`. An amount above zero that rounds to 0%
  prints as `<1%`, so spend is never shown as nothing.
- Per-day spend is total spend divided by the days in the window; under half
  a cent it prints as "under $0.01 a day".
- Budget percentages are recomputed as month-to-date spend over the effective
  cap (cap plus approved raise) and rounded to a whole number.

## Sections

1. **Title**: organization name, window dates, days, "UTC".
2. **Total**: spend, calls, tokens, per-day; then spend by capture source.
3. **By department**, **By project**: top 10 buckets by spend; the rest folded
   into one "Other (N more)" row.
4. **By model**: top 10 from the summary, with provider, calls and tokens.
5. **By person**: only when a per-person breakdown was fetched; it carries a
   line saying it is personal data.
6. **Budgets this month**: active keys, how many are capped, capped budget
   used; then each key at 80% or more, highest first; then uncapped keys that
   spent; then pending overage requests.
7. **Recommendations**.

A section with no data is left out. In a window with no usage the report says
so and still shows budgets, which are month-to-date.

## Recommendations (fixed, in this order)

| # | Fires when | Says |
|---|---|---|
| R0 | No calls and no spend in the window | Nothing to attribute. (R1, R2, R7, R8 are skipped.) |
| R1 | `(unassigned)` is 10% or more of spend | That share has no department; label keys or import the directory |
| R2 | At least one real project exists and `(no project)` is 25% or more | That share is not tied to a project |
| R3 | An active key is at 100% or more of its effective cap | Named keys are being answered `402 budget_exceeded`; raise the cap or decide the overage request |
| R4 | An active key is at 80% up to 100% | Named keys will be refused at 100% |
| R5 | An active key has no cap and spent this month | Count and amount; a cap is the only hard stop |
| R6 | Overage requests are pending | Count waiting on an admin or finance approver |
| R7 | One model is 60% or more of spend | Names it; an allowed-models list on a key enforces a cheaper choice where it fits |
| R8 | 20% or more of spend came from sources other than the gateway | Caps do not apply to that share |
| R9 | A breakdown was truncated | That table covers the 200 largest buckets only |

If nothing fires: "Nothing to flag."

**Small windows.** R1, R2, R7 and R8 are about shares of spend. When total
spend in the window is under $10 they are skipped, and one line says so:
a share of a few cents is not a finding. The budget rules (R3 to R6) and R9
are unaffected. The floor is `MIN_SPEND_FOR_SHARE_RULES` in the script.

Revoked keys never trigger a rule. The rules state facts and name the control
that exists in the product. They do not estimate savings, forecast spend, or
judge whether a team's spend is justified.
