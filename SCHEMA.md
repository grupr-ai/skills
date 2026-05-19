# Skill manifest schema

A Skill is a single JSON file at `skills/<id>.json`. This document describes
every field.

## Required fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | Lowercase, kebab-case. Must match the filename (`architect` → `architect.json`). Becomes the URL-addressable handle. |
| `name` | string | Human display name. Title-case. Shown in the Skill picker. |
| `version` | string | Semver. Bump per the CONTRIBUTING guide. |
| `author` | string | GitHub handle or org. |
| `category` | string | Top-level grouping. Launch categories: `code-review`. More to come. |
| `description` | string | One sentence on what this Skill watches for. Shown in search results. |
| `recommended_model` | object | `{ "provider": ..., "model_id": ... }`. Picked when the user doesn't override. |
| `system_prompt` | string | The full system prompt. Should be self-contained and produce output matching `output_contract`. |
| `output_contract` | string | What this Skill returns + format. Strict-format prompts make panels composable. |
| `tags` | array of string | Lowercase, hyphenated. Used for filtering + discovery. |
| `license` | string | SPDX identifier. Apache-2.0 default. |

## Optional fields

| Field | Type | Notes |
|---|---|---|
| `homepage` | string | URL — usually the github.com/grupr-ai/skills file. |
| `notes` | string | Free-form. Constraints, gotchas, ordering requirements (e.g. Synthesizer must run last). |
| `tool_requirements` | array | (v1.1, not yet stable) — Anthropic tool defs the Skill expects to have access to. |

## `recommended_model.provider` values

Currently accepted: `anthropic` · `openai` · `google` · `groq` · `perplexity` ·
`custom`. The Grupr platform enforces this list at API time. If you need a
provider not on this list, propose it in a separate issue first.

## Validation

```bash
# Coming soon:
npm run validate
# OR
python3 scripts/validate.py skills/your-id.json
```

For now, validate manually:

1. Manifest must be parseable JSON.
2. `id` must match filename.
3. All required fields present.
4. `recommended_model.provider` is in the allowed list.
