---
name: grupr-ai-spend-report
description: Report an organization's AI spend from Grupr Analytics, read-only - total spend, by department, project, model and capture source, virtual-key budgets against their monthly caps, and pending overage requests - for the last N days. Use when the user asks where the AI budget went, which team or project spent what on LLMs, which keys are near or over their cap, or wants a monthly AI spend report from Grupr Analytics.
license: Apache-2.0
metadata:
  version: "0.1.0"
  author: Grupr
  homepage: https://docs.grupr.ai/analytics-api
---

# Grupr AI spend report

Grupr Analytics attributes an organization's AI usage to departments,
projects, models and (optionally) people, and enforces monthly caps on the
virtual keys teams use. This skill turns those numbers into a short report in
dollars: what was spent, where, which keys are near or over their cap, and
what an admin should look at.

It is **read-only**. The API it calls has no write endpoints, and the token it
uses cannot call the gateway, spend money or change a setting. The skill never
posts, emails or publishes the report; it prints it for the user.

## When to use

Activate when the user asks any of:

- "Where did our AI budget go last month?"
- "Which team / project / model is spending the most on LLMs?"
- "Which keys are close to their cap?" / "Is anyone over budget?"
- "Give me the monthly AI spend report from Grupr."

Do not use it for a single agent's sandbox time or routine health; that is the
`grupr-agent-usage-report` skill, and those numbers are not money.

## Prerequisites

- A Grupr Analytics organization with usage in it.
- An **Analytics read token** (`gar_…`). An org admin creates one in the Grupr
  web app: Analytics, API read tokens, Create token. It is shown once.
- The token in the `GRUPR_ANALYTICS_TOKEN` environment variable of the shell
  that runs the script. **Never ask the user to paste the token into the chat,
  never echo it, never put it in a command line, a file or a URL.** If it is
  not set, tell the user to set it themselves and stop.
- Python 3.9 or newer. No third-party packages.

Per-person usage is off unless the admin ticked "Include per-person usage"
when creating the token. Do not ask for it unless the user wants a by-person
table; it is personal data.

No Grupr account is needed to run the tests or see a sample: `fixtures/` holds
labelled sample data.

## Steps

### 1. Fix the window

Default 30 days. Accept 1 to 366, or explicit dates. Days are UTC. Say the
window in the report.

### 2. Fetch, read-only

```
python -I scripts/spend_report.py fetch --out ./spend-export --days 30
```

This makes six GET requests to `https://api.grupr.ai/api/v1/analytics` (token
info, usage summary, breakdowns by department, project and capture source,
and key budgets) and saves each JSON response in the folder. Add `--people`
only when the user asked for a by-person table; the script skips it when the
token does not allow it. Use `--since 2026-10-01 --until 2026-11-01` for a
calendar month (`until` is exclusive).

What the script will not do: send the token anywhere but `api.grupr.ai`,
follow a redirect, print the token, or write it to disk. The saved files hold
the organization's spend, so keep the folder out of repositories and delete it
when the report is done.

### 3. Report

```
python -I scripts/spend_report.py report --dir ./spend-export
```

It prints Markdown to stdout (exit 0; exit 2 when `summary.json` is missing or
malformed). No network. The report has this shape, every time:

```
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

## Budgets this month (as of 2026-11-09)
- 4 active keys; 3 have a monthly cap; $2,263.80 of $2,800.00 capped budget used (81%)
- support-bot (Support): $512.30 of $500.00 (102%)
- eng-shared (Engineering): $1,710.40 of $2,000.00 (86%)
- 1 key without a cap spent $233.05

## Recommendations
- 14% of spend ($881.50) has no department. Label the virtual keys with a department, or import the directory, so it rolls up to a team.
- 1 key is at or over this month's cap, so the gateway answers 402 budget_exceeded: support-bot (Support) at 102%. Raise the cap or decide the overage request.
```

(Shortened; the full sample is `fixtures/expected-report.md`. The sample is
invented data, not a customer.)

Give the user the report as printed. Do not add numbers the script did not
produce, and do not round or restate them differently.

### 4. Read it honestly

- **Spend is what Grupr recorded**, priced from token counts. The provider
  invoice is the financial record. Grupr's own reconciliation view compares
  the two; it is not available through a read token.
- **Capture source matters.** `gateway` is traffic routed through Grupr and is
  the only spend a cap can stop. `telemetry` and `provider-reported` usage is
  counted but cannot be blocked.
- **Budgets are this calendar month (UTC)**, gateway spend only, against the
  key's cap plus any approved temporary raise. They do not follow the
  report's window.
- **A breakdown returns at most 200 buckets**, largest first. If the report
  says a table was truncated, its rows are not the whole picture.
- The recommendations come from a fixed rule set in
  `references/report-rules.md`. They never estimate savings or forecast
  spend. Do not add such estimates yourself.

### 5. Do not distribute it unasked

The report contains the organization's spend. Print it for the user. Post it,
email it or save it somewhere shared only if the user asks, and say where it
will go before doing it.

## Errors

| Exit | Message | Meaning |
|---|---|---|
| 2 | `GRUPR_ANALYTICS_TOKEN is not set` | The user sets it in their shell; never ask for the value |
| 2 | `does not hold an Analytics read token` | The variable holds some other credential (an agent token or a virtual key) |
| 2 | `refusing to send the read token to …` | A base URL other than `https://api.grupr.ai` was given |
| 3 | `401 unauthorized` | The token is wrong, expired or revoked; an org admin creates a new one |
| 3 | `403 people_not_allowed` | The token was created without per-person access |
| 3 | `429 rate_limited` | 60 requests a minute per token; wait the stated seconds |
| 3 | `400 invalid_since`, `invalid_range`, `range_too_large` | Fix the dates; the window may span at most 366 days |

## Limitations

- One organization per token. There is no cross-organization roll-up.
- No per-request detail, prompts or responses: totals and groupings only.
- Spend that never reached Grupr (seat licences, tools not routed through the
  gateway and not reporting telemetry) is not in the numbers.
- History is limited by the organization's data-retention setting.
- The API is described in `references/analytics-read-api.md`.
