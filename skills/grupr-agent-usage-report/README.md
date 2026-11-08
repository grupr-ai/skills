# grupr-agent-usage-report

A read-only agent skill that reports how one Grupr agent used its sandbox and
daily budget: sandbox time against the cap, denied and failed commands, routine
health, connection refusals, and what is waiting on the owner. It never reports
money, never runs commands, and writes nothing unless the user asks for the
report to be saved to Room Files and approves that one write.

The skill is the instructions in `SKILL.md`. The agent follows them with the
Grupr MCP connector, or offline over JSON saved from the agent hub.

## Layout

```
SKILL.md                      the skill (name, description, steps, limits)
references/
  agent-hub-usage-endpoints.md  the four GET endpoints, fields, auth, limits
  report-rules.md               formatting and recommendation rules
scripts/usage_report.py       offline report from saved JSON (stdlib only)
fixtures/                     sanitized sample responses + expected-report.md
tests/test_usage_report.py    unit tests and a golden-file test
```

## Try it without a Grupr account

```
python -I scripts/usage_report.py --dir fixtures --name "Reviewer's agent"
python -I -m unittest discover -s tests -v
```

`-I` runs Python in isolated mode so nothing in the current directory is
imported by accident. Python 3.9 or newer; no third-party packages.

## Install (not yet published)

This skill is prepared for distribution through the skills.sh CLI. Once the
publication destination is approved, the install line will be of the form

```
npx skills add OWNER/REPO --skill grupr-agent-usage-report -a claude-code
```

and will be filled in here and in the Grupr docs. Until then, copy the
`grupr-agent-usage-report` folder into your agent's skills directory
(for Claude Code: `.claude/skills/`).

### Telemetry

The skills.sh CLI sends the skill name, skill files and a timestamp when a
skill is installed from a repository that GitHub confirms is public; no
personal or device information. Set `DISABLE_TELEMETRY=1` (or `DO_NOT_TRACK=1`)
before `npx skills ...` to send nothing, which is what the maintainers do when
testing installs. The skill itself has no telemetry.

## What it reads

Through the connector: `grupr_workspace_summary`, `grupr_workspace_info`,
`grupr_workspace_schedules`, `grupr_workspace_schedule_runs`. All are marked
read-only in the connector's tool annotations. Offline: the same data saved
from `GET /api/v1/agent-hub/workspace`, `/workspace/summary`,
`/workspace/schedules` and `/workspace/schedules/{id}/runs` with an agent
token that the owner holds in an environment variable.

The credential sees exactly one agent. There is no cross-agent or account
view in this skill, and no dollar amounts anywhere.

## License

Proposed: Apache-2.0, the same as this repository. Pending maintainer
approval before publication.
