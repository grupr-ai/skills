# Report rules

The same rules the script applies, written out so an agent can produce the
report from connector output without running anything.

## Formatting

- Durations: under 60 minutes as `N min`; whole hours as `H h`; otherwise
  `H h M min`. Round to the nearest minute.
- Averages: minutes per day = sandbox_seconds / 60 / days, one decimal only if
  under 10, otherwise whole minutes; written as "about N min a day".
- Percentages: whole numbers; omit when the denominator is 0.
- Dates: `YYYY-MM-DD`; state that the window is in UTC.

## Sections and when they appear

| Section | Appears when |
|---|---|
| Sandbox time | always (0 is a valid report) |
| Commands | `runs` present |
| Routines | `routines_active > 0` or `firings > 0` |
| Connections | `connections > 0` or `connection_uses > 0` |
| Files and messages | either count > 0 |
| Waiting on the owner | `pending_requests > 0` or `waiting_long > 0` |
| Recommendations | always; "Nothing to flag." when no rule fires |

## Recommendation rules (apply in this order, each at most once)

R0 Idle: `sandbox_seconds == 0` and `runs == 0` and `firings == 0` →
"The agent did nothing in this window; there is nothing to budget."
Skip R1 to R3.

R1 No budget: `budget_seconds` absent and `sandbox_seconds > 0` →
"No daily sandbox budget is set. Based on about X min a day, a budget of
Y min would leave headroom without blocking normal work." Y = average daily
minutes × 1.5, rounded up to the next 5 minutes, at least 5, at most 1440.

R2 Budget reached and tight: `budget_hit` true and average daily minutes ≥
80% of budget minutes → "The budget is tight: average use is P% of the cap
and it was reached at least once. Raise it or move the heaviest routine to a
quieter hour."

R3 Budget reached on a spike: `budget_hit` true and average daily minutes <
80% of budget minutes → "The budget was reached at least once but average use
is only P% of the cap: a spike, not a trend. Check the routine firings on that
day before changing the cap."

R4 Denied commands: `runs_denied > 0` → "N command(s) were denied by a person
in this window. Read those approval cards before retrying anything similar."

R5 Failing commands: `runs ≥ 5` and `runs_failed / runs ≥ 0.2` → "N of M runs
failed (P%). Look at the failed runs' stderr before adding more automation."

R6 Failing routines: `routines_failing > 0` → "N routine(s) are failing now;
after 3 consecutive failures Grupr posts a room note and emails the owner, and
after 20 the routine pauses itself. Read grupr_workspace_schedule_runs for
each before saying it is healthy." If `schedules.json` is available, name
each routine with `failures > 0` and its `last_status` / `last_exit_code`.

R7 Paused routines: `routines_paused_self > 0` → "N routine(s) paused
themselves after repeated failures; they stay paused until the owner resumes
them."

R8 Refused connections: `connection_refused > 0` → "A stored connection was
refused N time(s) (401/403 from the remote host). Grupr notes the room after
3 refusals; the owner should re-check that credential."

R9 Owner backlog: `pending_requests > 0` or `waiting_long > 0` → "N item(s)
are waiting on the owner (M for more than a week): requests, cards or paused
routines. They show under Waiting on you in Grupr."

## What never goes in the report

- Money, prices or cost estimates.
- Token counts (not available).
- Guesses about what a denied command was for.
- Anything about other agents or the owner's account.
