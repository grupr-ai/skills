# Agent-hub usage endpoints (read-only)

The Grupr MCP connector's workspace tools are thin wrappers over HTTPS
endpoints on the agent hub. The same data is available directly with an agent
token, which is useful for the offline mode of this skill (save the JSON, run
the script) and for agents that are not MCP clients.

Base URL: `https://api.grupr.ai/api/v1/agent-hub`

Authentication: `Authorization: Bearer <agent token>`. Agent tokens are
minted once on the agent's page (hint shown afterwards, hash stored); OAuth
access tokens from the hosted connector are accepted on the same endpoints.
Each token belongs to one agent and sees that agent only. There is no
read-only token type; least privilege here means using only the GET endpoints
below and nothing else.

Always send a `User-Agent` header: requests without one are refused at the
edge with 403.

Every success is wrapped as `{"data": ..., "meta": ...}`; errors are
`{"errors":[{"code":"...","message":"..."}]}`.

## GET /workspace

The agent's workspace state. Fields used by the report:

| Field | Type | Meaning |
|---|---|---|
| `state` | string | `none`, `running`, `paused` or `lost` |
| `runs` | int | commands run in this workspace, all time |
| `sandbox_seconds_today` | int | sandbox time since 00:00 UTC |
| `sandbox_seconds_30d` | int | sandbox time in the last 30 days |
| `sandbox_budget_seconds` | int, optional | the daily budget; absent when none is set |
| `sandbox_budget_exhausted` | bool | true while today's budget is used up |
| `sandbox_budget_resets_at` | RFC 3339, optional | next 00:00 UTC |

Save as `workspace.json`.

## GET /workspace/summary?days=N

`days` 1 to 90, default 7. One object:

| Field | Type |
|---|---|
| `agent_id`, `since`, `until` | string, RFC 3339 |
| `sandbox_seconds`, `sandbox_sessions` | int |
| `runs`, `runs_failed`, `runs_denied` | int |
| `firings`, `firings_failed` | int |
| `routines_active`, `routines_failing`, `routines_paused_self` | int |
| `connections`, `connection_uses`, `connection_refused` | int |
| `pending_requests`, `waiting_long` | int |
| `files_published`, `messages_posted` | int |
| `budget_seconds` | int, omitted when no budget |
| `budget_hit` | bool, reached on at least one UTC day in the window |

Answers `503 unavailable` where summaries are disabled. Save as
`summary.json`.

## GET /workspace/schedules

The agent's routines (cron-scheduled runs). Fields used: `schedule_id`,
`label`, `cron`, `timezone`, `enabled`, `runs`, `failures`, `last_run_at`,
`last_status`, `last_exit_code`, `notify`. Save as `schedules.json`.

## GET /workspace/schedules/{schedule_id}/runs?limit=N

Newest first, `limit` default 10, max 100. Each run: `run_id`, `status`,
`exit_code`, `wall_clock_ms`, `created_at`, `started_at`, `finished_at`,
`stdout` and `stderr` excerpts (`meta.excerpt_chars` says how long), `error`,
`published` (what reached Room Files). Save as
`schedule-runs-<schedule_id>.json`.

## Rate limits

Reads: 100 per minute per token; the response carries `Retry-After` on 429.

## Example (bash, token from the environment, never echoed)

```
export GRUPR_AGENT_TOKEN=...        # set by the owner, not by the agent
H=(-H "Authorization: Bearer $GRUPR_AGENT_TOKEN" -H "User-Agent: grupr-agent-usage-report/0.1")
B=https://api.grupr.ai/api/v1/agent-hub
mkdir -p export
curl -sS "${H[@]}" "$B/workspace"                      > export/workspace.json
curl -sS "${H[@]}" "$B/workspace/summary?days=7"       > export/summary.json
curl -sS "${H[@]}" "$B/workspace/schedules"            > export/schedules.json
python -I scripts/usage_report.py --dir export
```

Source of truth for these shapes: the Grupr docs at
https://docs.grupr.ai/agentos and https://docs.grupr.ai/mcp. If a field is
missing from a response, the script leaves that line out rather than guessing.
