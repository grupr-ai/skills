# Grupr Skills

> The community registry of **Skills** — reusable, contributable, mix-and-match
> reviewer agents for [Grupr](https://grupr.ai) Code Review and beyond.

Skills are the primitive that make Grupr panels work. A Skill is a small JSON
manifest that combines a **system prompt**, a **recommended model**, and an
**output contract** into one composable unit. Drop a Skill into a Code Review
panel and the platform handles the rest: dispatch, BYOK key resolution,
streaming, and the Synthesizer's consensus over your full panel.

This repo is the canonical index. Skills here can be referenced by `id` from:

```bash
# Coming soon — npx grupr review CLI
npx grupr review ./diff.patch --skills architect,security,performance,maintainability,synthesizer

# Or via the Grupr web app
https://app.grupr.ai/code-review/new
```

## The 5 launch Skills

| Skill | Default model | What it watches |
|---|---|---|
| **[Architect](./skills/architect.json)** | Claude Opus 4 | Structure, abstractions, coupling, naming |
| **[Security](./skills/security.json)** | GPT-4o | OWASP Top 10, injection, secrets, auth |
| **[Performance](./skills/performance.json)** | Claude Sonnet 4.5 | Algorithmic complexity, hot paths, N+1, caching |
| **[Maintainability](./skills/maintainability.json)** | GPT-4o-mini | Readability, dead code, naming, test gaps |
| **[Synthesizer](./skills/synthesizer.json)** | Claude Opus 4 | One unified verdict + explicit disagreements |

The default panel runs **all 5** and is what `npx grupr review` uses out of
the box. Override any Skill's model in your Grupr account settings, or
publish your own Skill (see below).

## Why a panel, not a single model

A single model misses things outside its training emphasis. From our own
suite-1 internal data on 4 bot-built apps:

- **All 4 envs surfaced reviewer disagreements** — some Skills voted *ship*
  on the same code another Skill voted *block*.
- The Synthesizer's job is to surface these disagreements rather than hide
  them, so the human (or the patcher) sees the actual tradeoff.

> *"Generic agents plateau fast. Reusable playbooks are what make behavior
> compound instead of resetting every session."* — [@geren8te on the
> Browserbase skills launch](https://x.com/geren8te/status/...) — the same
> principle applies to code review.

## Skill manifest format

A Skill is one JSON file at `skills/<id>.json`. See
[`SCHEMA.md`](./SCHEMA.md) for the full field reference. Minimum viable
shape:

```json
{
  "id": "your-skill-id",
  "name": "Your Skill",
  "version": "1.0.0",
  "author": "your-github-handle",
  "category": "code-review",
  "description": "One sentence on what this Skill watches for.",
  "recommended_model": {
    "provider": "anthropic",
    "model_id": "claude-sonnet-4-5-20250929"
  },
  "system_prompt": "Your prompt here…",
  "output_contract": "What this Skill returns and how it's formatted.",
  "tags": ["code-review", "your-tag"],
  "license": "Apache-2.0"
}
```

## Contribute a Skill

We accept Skills via PR. Three rules:

1. **One Skill per PR.** Keep reviews focused.
2. **Apache-2.0 license** on the manifest (the Skill content itself —
   you're free to license downstream artifacts however).
3. **One sentence describing the gap** your Skill fills that the 5 launch
   Skills don't. Examples we'd love: Accessibility · Database schema ·
   API breaking-change detection · Migration safety · Cost-of-LLM-calls ·
   Test quality.

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for the full PR template.

## License

Apache-2.0 — see [`LICENSE`](./LICENSE).

Individual Skills are licensed by their `license` field; default for this
repo is Apache-2.0 unless a Skill manifest declares otherwise.
