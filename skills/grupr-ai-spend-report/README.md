# grupr-ai-spend-report

A read-only agent skill that reports an organization's AI spend from Grupr
Analytics: total, by department, project, model and capture source, each
virtual key's budget against its monthly cap, and what is waiting on an
approver. It reads through the public Analytics read API with a read token
that cannot spend or change anything.

The skill is the instructions in `SKILL.md`. The agent runs one script to
fetch and one to report.

## Layout

```
SKILL.md                        the skill (name, description, steps, limits)
references/
  analytics-read-api.md         the four GET endpoints, auth, limits, errors
  report-rules.md               formatting and the fixed recommendation rules
scripts/spend_report.py         fetch (network) and report (offline); stdlib only
fixtures/                       labelled sample responses + expected-report.md
tests/test_spend_report.py      unit tests, a golden-file test, fetch tests against a local stub
```

## Try it without a Grupr account

```
python -I scripts/spend_report.py report --dir fixtures
python -I -m unittest discover -s tests -v
```

`-I` runs Python in isolated mode so nothing in the current directory is
imported by accident. Python 3.9 or newer; no third-party packages. The
fixtures are invented sample data ("Northwind Holdings (sample)"), not a
customer's numbers.

## Use it for real

1. An org admin creates a read token in the Grupr web app: Analytics, API read
   tokens, Create token. Choose an expiry. Leave "Include per-person usage"
   off unless you need a by-person table.
2. Put it in your shell, not in a file or a chat:

   ```
   export GRUPR_ANALYTICS_TOKEN=...   # the gar_ token, shown once
   ```

3. Fetch and report:

   ```
   python -I scripts/spend_report.py fetch --out ./spend-export --days 30
   python -I scripts/spend_report.py report --dir ./spend-export
   ```

4. Delete `./spend-export` when you are done. It holds your spend data.

## What it sends and where

`fetch` makes GET requests to `https://api.grupr.ai/api/v1/analytics` only,
with the token in the `Authorization` header and a `User-Agent` of
`grupr-ai-spend-report/<version>`. It refuses any other host, does not follow
redirects, and never prints the token or writes it to disk. `report` makes no
network calls. The skill has no telemetry of its own.

## Install

From the public `grupr-ai/skills` repository with the skills.sh CLI
(Node 22.20 or newer):

```
npx skills add grupr-ai/skills --skill grupr-ai-spend-report -a claude-code
```

Use `-a codex`, `-a cursor` or another agent id for other clients, or omit
`-a` to choose among the agents the CLI detects. Without the CLI, copy this
folder into your agent's skills directory (for Claude Code: `.claude/skills/`).

### Telemetry

The skills.sh CLI sends the skill name, skill files and a timestamp when a
skill is installed from a repository that GitHub confirms is public; no
personal or device information. Set `DISABLE_TELEMETRY=1` (or
`DO_NOT_TRACK=1`) before `npx skills ...` to send nothing.

## Limits

One organization per token; totals and groupings only (no prompts, no
per-request rows); spend that never reached Grupr is not in the numbers; the
provider invoice remains the financial record. See `SKILL.md`.

## License

Apache-2.0, as the repository.
