# Contributing a Skill

Skills live as JSON manifests at `skills/<id>.json`. This guide is the PR
template for adding one.

## Quick path

1. Fork this repo.
2. Add your Skill at `skills/<your-id>.json` following the
   [schema](./SCHEMA.md).
3. Run `npm run validate` (or `python3 scripts/validate.py`) locally to
   confirm your manifest parses + matches the schema.
4. Add a row to the table in `README.md` under "The 5 launch Skills" or
   in a new "Community Skills" section if you're adding the first one.
5. Open a PR with the title `feat(skill): <Skill name> — <one-line gap>`.

## PR review checklist

We're looking for:

- [ ] **A real gap.** What does this Skill watch for that the 5 launch
      Skills don't? One sentence in the PR description.
- [ ] **Model is reasonable.** `recommended_model` points to something
      actually available across Anthropic / OpenAI / Google / Groq.
      Don't ship a manifest pointing at a private fine-tune.
- [ ] **System prompt is self-contained.** It assumes only the code
      under review + (optionally) prior Skill verdicts in the panel.
      No assumptions about external tools unless declared in
      `tool_requirements` (coming v1.1).
- [ ] **Output contract is explicit.** What does the Skill return? Markdown
      headers, JSON, plain prose? Strict-format prompts make panels
      composable.
- [ ] **License is set.** Apache-2.0 is the default; you can declare
      anything OSS-compatible.
- [ ] **Tags help discovery.** Use lowercase, hyphenated tags. Reuse
      existing ones where possible.

## What we don't accept (yet)

- Skills that require platform-side code changes to integrate.
- Skills with closed/proprietary system prompts. The point of a public
  registry is auditability — if you don't want your prompt readable,
  this isn't the place for it.
- Skills that duplicate one of the 5 launch Skills without a clear
  differentiator.

## Versioning

`version` follows semver. Bump:

- **Patch** for typo fixes to the prompt that don't change behavior.
- **Minor** for prompt tuning that changes the output but keeps the
  contract.
- **Major** for breaking changes to the `output_contract`.

We may eventually pin specific Skill versions in panel configs. For now,
the registry always serves `main`.

## Questions

File an issue with the `discussion` label, or DM
[@grupr_ai](https://x.com/grupr_ai) on X.
