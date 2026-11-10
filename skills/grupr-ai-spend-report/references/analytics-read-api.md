# Grupr Analytics read API

Public, read-only. Base URL `https://api.grupr.ai/api/v1/analytics`. Full
reference: https://docs.grupr.ai/analytics-api

## Authentication

`Authorization: Bearer gar_…` with an **Analytics read token**. An org admin
creates one in the web app (Analytics, API read tokens); it is shown once and
stored hashed. The token is bound to one organization, and the organization a
request reads is taken from the token: there is no org id to pass.

A read token can read usage rollups and key budgets. It cannot call the
gateway, cannot write anything, and is refused by every other Grupr API. Other
credentials (session, agent token `gat_`, connector token `goa_`, virtual key
`gvk_`) are refused here.

Send a `User-Agent` header; requests without one are refused at the edge
before they reach Grupr.

## Endpoints (all GET)

| Path | Returns |
|---|---|
| `/` | The organization, the token's name, expiry and whether it may read per-person usage, the dimensions it may group by, and the maximum window |
| `/usage/summary?since=&until=` | `totals` (`calls`, `total_tokens`, `cost_usd`) and `by_model` (provider, model, calls, tokens, `cost_usd`) |
| `/usage/breakdown?dimension=&since=&until=` | `rows` (`bucket`, `calls`, `total_tokens`, `cost_usd`), `totals` for those rows, `truncated` |
| `/budgets` | Every virtual key's cap and month-to-date gateway spend, `totals`, `pending_overage_requests` |

Responses are wrapped as `{"data": …}`. Errors are
`{"errors":[{"code","message","field"?}]}`.

### Window

`since` and `until` are RFC 3339 times or `YYYY-MM-DD` dates (UTC midnight);
`until` is exclusive. Default: the 30 days ending now. A value that does not
parse is `400 invalid_since` / `invalid_until`, not a silent default. `since`
must be before `until` (`400 invalid_range`) and the window may span at most
366 days (`400 range_too_large`).

### Breakdown dimensions

`department`, `sub_department`, `project`, `function`, `model`, `provider`,
`tag`, `source`, and `user`. Any of them can also be passed as a filter, for
example `?dimension=model&department=Engineering`.

- `user` (as a dimension or a filter) needs a token created with per-person
  access; otherwise `403 people_not_allowed`.
- `function` groups by job title from the directory. In a small organization a
  title can identify one person even without the `user` dimension.
- Buckets with no value are named: `(unassigned)` for department,
  `(no project)`, `(untagged)`, `(unattributed)`, `(unclassified)`.
- At most 200 buckets come back, largest spend first; `truncated` is true when
  the limit was reached, and `totals` then covers those 200 only.
- `source` is where the usage was captured: `gateway`, `otel` (telemetry),
  `provider_api` (provider-reported) or `agent`.

### Budgets

Per key: `key_id`, `name`, `department`, `team`, `tag`, `status`
(`active` / `revoked`), `monthly_cap_usd` (null = no cap),
`approved_raise_usd`, `effective_cap_usd` (cap plus approved, unexpired
raises), `spend_mtd_usd`, `remaining_usd`, `percent_used`, `last_used_at`.

Spend is gateway traffic since the first of the month, UTC: the same basis
the gateway enforces caps on. No key material is returned (not the key, its
hash or its display hint).

## Limits

- 60 requests a minute per token (`429 rate_limited`, with
  `retry_after_seconds` and a `Retry-After` header).
- Responses are `Cache-Control: private, no-store`.
- At most 20 live tokens per organization; tokens can expire (1 to 365 days)
  and can be revoked at any time by an org admin.

## Status codes

| Status | Code | When |
|---|---|---|
| 401 | `unauthorized` | No token, wrong kind of credential, or the token is unknown, expired or revoked |
| 403 | `people_not_allowed` | Per-person usage asked for with a token that does not allow it |
| 400 | `invalid_dimension`, `invalid_since`, `invalid_until`, `invalid_range`, `range_too_large` | Bad request, with the field named |
| 429 | `rate_limited` | Over 60 requests a minute |
