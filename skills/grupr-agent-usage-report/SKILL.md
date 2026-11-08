---
name: grupr-agent-usage-report
description: Report how a Grupr agent used its sandbox and daily budget - sandbox time versus the daily cap, runs, denied and failed commands, routine health, connection refusals - over the last N days, read-only, through the Grupr MCP connector or a saved JSON export. Use when the user asks how much sandbox time an agent used, whether it hit its budget, why a routine keeps failing, or wants a weekly usage summary of a Grupr agent.
license: Apache-2.0
metadata:
  version: "0.1.0"
  author: Grupr
  homepage: https://docs.grupr.ai/guides/agent-usage-report
---

# Grupr agent usage report

Grupr gives every agent a rented Linux sandbox that pauses when idle, and lets
the owner cap it with a **daily sandbox budget** (5 minutes to 24 hours per UTC
day). This skill turns the numbers Grupr already keeps about one agent into a
short, honest report: how much sandbox time it used against that budget, which
commands were denied or failed, whether its routines are healthy, and what is
waiting on the owner.

It is **read-only by default**. Nothing is changed, scheduled, posted or
published unless the user asks for the report to be saved to Room Files, and
that single write needs their explicit approval first.

## When to use

Activate when the user asks any of:

- "How much sandbox time did my agent use this week?"
- "Did <agent> hit its daily budget?"
- "Why does this routine keep failing?" / "Are the routines healthy?"
- "Give me a usage summary for <agent> for the last 30 days."

Do not use it for Grupr Analytics (organization AI spend in dollars): that is a
different product with no public API, and this skill never reports money.

## Prerequisites

One of:

- **Connector mode (preferred):** the Grupr MCP connector is connected
  (Claude: the Grupr connector from the directory, or a custom connector at
  `https://api.grupr.ai/mcp`; other clients: the same URL or the
  `@grupr/mcp-server` package with an agent token). The connector speaks as the
  one agent the owner chose at consent; you see that agent only.
- **Offline mode:** the user gives you JSON saved from the agent-hub HTTPS
  endpoints (see `references/agent-hub-usage-endpoints.md`), or you fetch them
  with an agent token held in an environment variable. Never ask for, echo or
  store the token.

No Grupr account is needed to run the tests; `fixtures/` has sample data.

## Steps

### 1. Fix the window

Default 7 days. Accept 1 to 90. Say the window and the UTC day boundary in the
report; the daily budget resets at 00:00 UTC.

### 2. Gather, read-only

Connector mode, in this order:

1. `grupr_workspace_summary` with `days` set. It returns the agent's own
   numbers: sandbox time and sessions, runs (failed, denied), routine firings
   (failed, routines failing now, routines that paused themselves), connection
   uses (refused), files published, and whether the daily budget was reached.
2. `grupr_workspace_info` for today: `sandbox_seconds_today`,
   `sandbox_budget_seconds` and `sandbox_budget_resets_at` (absent when no
   budget is set), plus state and run count.
3. `grupr_workspace_schedules` for the routine list, then
   `grupr_workspace_schedule_runs` (`limit` up to 100, newest first) **only for
   routines that show failures**; each firing has an exit code, duration and an
   output excerpt.

Offline mode: put the saved responses in one folder as `summary.json`,
`workspace.json`, `schedules.json` and `schedule-runs-<schedule_id>.json`, then
run:

```
python -I scripts/usage_report.py --dir ./export
```

The script is stdlib-only, makes no network calls, and prints the Markdown
report to stdout (exit 0; exit 2 on a missing or malformed `summary.json`).

### 3. Compute

Apply `references/report-rules.md` exactly, by hand in connector mode or via
the script offline. Headline numbers:

- average sandbox minutes per day = `sandbox_seconds / 60 / days`
- budget utilisation = average daily minutes / budget minutes (only when a
  budget exists)
- run failure rate = `runs_failed / runs`; routine failure rate =
  `firings_failed / firings` (omit a rate when the denominator is 0)

### 4. Report

Use this shape, every time:

```
# Agent usage report: Reviewer's agent, 2026-11-01 to 2026-11-08 (7 days, UTC)

## Sandbox time
- Used: 3 h 12 min in 9 sessions (about 27 min a day)
- Daily budget: 1 h; reached on at least one day in this window
- Today: 14 min of 1 h (resets 00:00 UTC)

## Commands
- 41 runs; 3 failed (7%); 2 denied by a person

## Routines
- 4 active; 1 failing now; 56 firings; 5 failed (9%)
- nightly-site-check: 28 firings, 5 failures, last run failed (exit 1)

## Connections
- 12 uses across 2 connections; 1 refused

## Files and messages
- 6 files published; 23 messages posted

## Waiting on the owner
- 1 pending request; 0 waiting longer than a week

## Recommendations
- The budget was reached at least once but average use is only 46% of the cap: a spike, not a trend. Check the routine firings on that day before changing the cap.
- 2 commands were denied by a person in this window. Read those approval cards before retrying anything similar.
- 1 routine is failing now; after 3 consecutive failures Grupr posts a room note and emails the owner, and after 20 the routine pauses itself. Read grupr_workspace_schedule_runs for each before saying it is healthy. Routines with failures: nightly-site-check (last run: "HTTP 503 from https://example.com after 3 retries").
- A stored connection was refused 1 time (401/403 from the remote host). Grupr notes the room after 3 refusals; the owner should re-check that credential.
- 1 item is waiting on the owner (0 for more than a week): requests, cards or paused routines. They show under Waiting on you in Grupr.
```

Only include a section when its numbers exist. Quote excerpts from routine
runs verbatim and short.

### 5. Save it, only if asked

If the user wants the report in the room, say exactly what will be written
(`grupr_room_doc_write`, the room, the file name) and wait for a yes. That is
the only write this skill ever makes. Never post it with `grupr_send_message`
unasked; never schedule anything.

## Reading the numbers honestly

- Sandbox time is counted from start or resume to pause; a sandbox that stayed
  open after a command counts until it paused.
- `budget_hit` means the budget was reached on at least one UTC day in the
  window, not that it is exhausted now; `sandbox_budget_exhausted` from
  `grupr_workspace_info` is the live state.
- A `runs_denied` count is a person saying no; report it, never argue with it.
- Routine firings that could not start because the budget was already used up
  are skipped, not failed; they appear in the room as a note, not in
  `firings_failed`.
- None of these numbers are money. Grupr plans are flat; sandbox time is a
  usage measure, not a charge.

## Limitations

- One agent at a time: the connector and the agent token see only the agent
  they belong to. Cross-agent or whole-account views exist on the owner's
  Agents → This week page and Monday email, not through this skill.
- No history beyond 90 days.
- No per-command cost or token counts.
- The summary endpoint can answer `503 unavailable` on a server where
  summaries are disabled; say so and stop.

## Errors you may see

| Where | Error | Meaning |
|---|---|---|
| any tool | `401 unauthenticated` | the token or OAuth grant is gone; the owner reconnects |
| `grupr_workspace_run`, file tools | `429 sandbox_budget` | today's budget is used up until 00:00 UTC (this skill never triggers it: it runs nothing) |
| summary | `503 unavailable` | summaries disabled on this server |
| HTTPS without a User-Agent | `403` at the edge | set a User-Agent header |

Reads are rate-limited to 100 a minute per token; this skill needs at most a
handful.
