# AI spend report: Northwind Holdings (sample), 2026-10-10 to 2026-11-09 (30 days, UTC)

## Total
- Spend: $6,184.37 across 18,420 calls and 412.6M tokens (about $206.15 a day)
- By capture source: gateway $4,884.37 (79%); telemetry $1,300.00 (21%)

## By department
| Department | Spend | Share | Calls |
|---|---:|---:|---:|
| Engineering | $3,410.12 | 55% | 9,800 |
| Support | $1,280.50 | 21% | 5,200 |
| (unassigned) | $881.50 | 14% | 1,520 |
| Marketing | $612.25 | 10% | 1,900 |

## By project
| Project | Spend | Share | Calls |
|---|---:|---:|---:|
| (no project) | $3,053.87 | 49% | 9,120 |
| Checkout rewrite | $1,850.00 | 30% | 4,100 |
| Support copilot | $1,280.50 | 21% | 5,200 |

## By model
| Model | Provider | Spend | Share | Calls | Tokens |
|---|---|---:|---:|---:|---:|
| claude-sonnet-5-5 | anthropic | $3,961.20 | 64% | 9,200 | 240.4M |
| gpt-5.6 | openai | $1,512.40 | 24% | 5,100 | 102.2M |
| gemini-3.8-flash | google | $590.77 | 10% | 2,900 | 55.0M |
| gpt-5.6-luna | openai | $120.00 | 2% | 1,220 | 15.0M |

## Budgets this month (as of 2026-11-09)
- 4 active keys; 3 have a monthly cap; $2,263.80 of $2,800.00 capped budget used (81%)
- support-bot (Support): $512.30 of $500.00 (102%)
- eng-shared (Engineering): $1,710.40 of $2,000.00 (86%)
- 1 key without a cap spent $233.05
- Budget spend counts gateway traffic only, the basis caps are enforced on
- 1 overage request waiting on an approver

## Recommendations
- 14% of spend ($881.50) has no department. Label the virtual keys with a department, or import the directory, so it rolls up to a team.
- 49% of spend ($3,053.87) is not tied to a project. Bind keys to a project, or map repositories to one, if project-level numbers matter to you.
- 1 key is at or over this month's cap, so the gateway answers 402 budget_exceeded: support-bot (Support) at 102%. Raise the cap or decide the overage request.
- 1 key has used 80% or more of this month's cap and will be refused at 100%: eng-shared (Engineering) at 86%.
- 1 key has no monthly cap and spent $233.05 this month. A cap is the only hard stop on a key.
- 1 overage request is waiting on an admin or finance approver.
- 64% of spend is one model (anthropic/claude-sonnet-5-5). If part of that work fits a cheaper model, an allowed-models list on the key enforces the choice.
- 21% of spend ($1,300.00) was captured from telemetry or provider reports, not the gateway. Monthly caps do not apply to it.
