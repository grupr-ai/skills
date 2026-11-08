#!/usr/bin/env python3
"""Offline Grupr agent usage report.

Reads JSON saved from the Grupr agent-hub (see
references/agent-hub-usage-endpoints.md) and prints a Markdown report that
follows references/report-rules.md. Standard library only; no network access;
never reads credentials.

    python -I usage_report.py --dir ./export
    python -I usage_report.py --summary summary.json [--workspace workspace.json]
                              [--schedules schedules.json] [--runs schedule-runs-*.json]

Exit codes: 0 report printed; 2 summary missing or malformed.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------------- loading


def load_json(path: str) -> Any:
    """Load a saved response, unwrapping the agent-hub {"data": ...} envelope."""
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    if isinstance(obj, dict) and "data" in obj and isinstance(obj["data"], (dict, list)):
        return obj["data"]
    return obj


def parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def window_days(summary: Dict[str, Any], fallback: int = 7) -> int:
    since, until = parse_ts(summary.get("since")), parse_ts(summary.get("until"))
    if since and until and until > since:
        return max(1, round((until - since).total_seconds() / 86400))
    return fallback


# -------------------------------------------------------------- formatting


def fmt_dur(seconds: Any) -> str:
    m = round((seconds or 0) / 60)
    if m < 60:
        return f"{m} min"
    if m % 60 == 0:
        return f"{m // 60} h"
    return f"{m // 60} h {m % 60} min"


def fmt_minutes(minutes: float) -> str:
    return f"{minutes:.1f}" if minutes < 10 else f"{round(minutes)}"


def pct(n: Any, d: Any) -> Optional[int]:
    if not d:
        return None
    return round(100 * (n or 0) / d)


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def date_only(value: Any) -> str:
    dt = parse_ts(value)
    return dt.strftime("%Y-%m-%d") if dt else "?"


def suggested_budget_minutes(avg_daily_minutes: float) -> int:
    """R1: 1.5x the daily average, up to the next 5 minutes, within 5..1440."""
    raw = avg_daily_minutes * 1.5
    rounded = int(math.ceil(raw / 5.0) * 5)
    return max(5, min(1440, rounded))


# ---------------------------------------------------------------- analysis


def failing_routines(schedules: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not schedules:
        return []
    return [s for s in schedules if (s.get("failures") or 0) > 0]


def last_failed_excerpt(runs: Optional[List[Dict[str, Any]]], limit: int = 90) -> Optional[str]:
    """Newest failed run's stderr (or stdout) excerpt, first line, trimmed."""
    for r in runs or []:
        failed = r.get("status") == "failed" or (r.get("exit_code") not in (None, 0))
        if not failed:
            continue
        text = (r.get("stderr") or r.get("stdout") or r.get("error") or "").strip()
        if not text:
            continue
        line = text.splitlines()[0].strip()
        return line if len(line) <= limit else line[: limit - 1] + "…"
    return None


def recommendations(
    s: Dict[str, Any],
    days: int,
    schedules: Optional[List[Dict[str, Any]]] = None,
    runs_by_sid: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[str]:
    out: List[str] = []
    sandbox = s.get("sandbox_seconds") or 0
    runs = s.get("runs") or 0
    firings = s.get("firings") or 0
    avg_min = sandbox / 60.0 / max(1, days)
    budget = s.get("budget_seconds")
    budget_min = (budget or 0) / 60.0

    idle = sandbox == 0 and runs == 0 and firings == 0
    if idle:
        out.append("The agent did nothing in this window; there is nothing to budget.")
    elif budget is None and sandbox > 0:
        y = suggested_budget_minutes(avg_min)
        out.append(
            f"No daily sandbox budget is set. Based on about {fmt_minutes(avg_min)} min a day, "
            f"a budget of {y} min would leave headroom without blocking normal work."
        )
    elif budget and s.get("budget_hit"):
        p = pct(avg_min, budget_min)
        if avg_min >= 0.8 * budget_min:
            out.append(
                f"The budget is tight: average use is {p}% of the cap and it was reached at least once. "
                "Raise it or move the heaviest routine to a quieter hour."
            )
        else:
            out.append(
                f"The budget was reached at least once but average use is only {p}% of the cap: a spike, "
                "not a trend. Check the routine firings on that day before changing the cap."
            )

    denied = s.get("runs_denied") or 0
    if denied:
        out.append(
            f"{plural(denied, 'command')} {'was' if denied == 1 else 'were'} denied by a person in this window. "
            "Read those approval cards before retrying anything similar."
        )

    failed = s.get("runs_failed") or 0
    if runs >= 5 and failed / runs >= 0.2:
        out.append(
            f"{failed} of {runs} runs failed ({pct(failed, runs)}%). Look at the failed runs' stderr before adding more automation."
        )

    failing_now = s.get("routines_failing") or 0
    if failing_now:
        line = (
            f"{plural(failing_now, 'routine')} {'is' if failing_now == 1 else 'are'} failing now; after 3 consecutive failures "
            "Grupr posts a room note and emails the owner, and after 20 the routine pauses itself. "
            "Read grupr_workspace_schedule_runs for each before saying it is healthy."
        )
        names = []
        for sch in failing_routines(schedules):
            label = sch.get("label") or sch.get("schedule_id") or "routine"
            excerpt = last_failed_excerpt((runs_by_sid or {}).get(sch.get("schedule_id") or ""))
            names.append(f'{label} (last run: "{excerpt}")' if excerpt else label)
        if names:
            line += " Routines with failures: " + "; ".join(names) + "."
        out.append(line)

    paused = s.get("routines_paused_self") or 0
    if paused:
        out.append(
            f"{plural(paused, 'routine')} paused {'itself' if paused == 1 else 'themselves'} after repeated failures; "
            f"{'it stays' if paused == 1 else 'they stay'} paused until the owner resumes {'it' if paused == 1 else 'them'}."
        )

    refused = s.get("connection_refused") or 0
    if refused:
        out.append(
            f"A stored connection was refused {plural(refused, 'time')} (401/403 from the remote host). "
            "Grupr notes the room after 3 refusals; the owner should re-check that credential."
        )

    pending = s.get("pending_requests") or 0
    waiting_long = s.get("waiting_long") or 0
    if pending or waiting_long:
        out.append(
            f"{plural(pending, 'item')} {'is' if pending == 1 else 'are'} waiting on the owner "
            f"({waiting_long} for more than a week): requests, cards or paused routines. "
            "They show under Waiting on you in Grupr."
        )

    return out or ["Nothing to flag."]


# ------------------------------------------------------------------ report


def build_report(
    summary: Dict[str, Any],
    workspace: Optional[Dict[str, Any]] = None,
    schedules: Optional[List[Dict[str, Any]]] = None,
    runs_by_sid: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    agent_name: Optional[str] = None,
    days: Optional[int] = None,
) -> str:
    s = summary
    n_days = days or window_days(s)
    who = agent_name or s.get("agent_id") or "agent"
    lines: List[str] = []
    lines.append(
        f"# Agent usage report: {who}, {date_only(s.get('since'))} to {date_only(s.get('until'))} "
        f"({plural(n_days, 'day')}, UTC)"
    )

    # Sandbox time (always)
    sandbox = s.get("sandbox_seconds") or 0
    sessions = s.get("sandbox_sessions") or 0
    avg_min = sandbox / 60.0 / max(1, n_days)
    lines += ["", "## Sandbox time"]
    lines.append(
        f"- Used: {fmt_dur(sandbox)} in {plural(sessions, 'session')} (about {fmt_minutes(avg_min)} min a day)"
    )
    budget = s.get("budget_seconds")
    if budget:
        hit = "reached on at least one day in this window" if s.get("budget_hit") else "not reached in this window"
        lines.append(f"- Daily budget: {fmt_dur(budget)}; {hit}")
    else:
        lines.append("- Daily budget: none set")
    if workspace:
        today = workspace.get("sandbox_seconds_today")
        if today is not None:
            wb = workspace.get("sandbox_budget_seconds")
            if wb:
                state = " (used up until 00:00 UTC)" if workspace.get("sandbox_budget_exhausted") else " (resets 00:00 UTC)"
                lines.append(f"- Today: {fmt_dur(today)} of {fmt_dur(wb)}{state}")
            else:
                lines.append(f"- Today: {fmt_dur(today)}")

    # Commands
    if "runs" in s:
        runs = s.get("runs") or 0
        failed = s.get("runs_failed") or 0
        denied = s.get("runs_denied") or 0
        parts = [plural(runs, "run")]
        if runs:
            p = pct(failed, runs)
            parts.append(f"{failed} failed ({p}%)")
        if denied:
            parts.append(f"{denied} denied by a person")
        lines += ["", "## Commands", "- " + "; ".join(parts)]

    # Routines
    active = s.get("routines_active") or 0
    firings = s.get("firings") or 0
    if active or firings:
        ffailed = s.get("firings_failed") or 0
        failing_now = s.get("routines_failing") or 0
        paused = s.get("routines_paused_self") or 0
        parts = [f"{active} active"]
        if failing_now:
            parts.append(f"{failing_now} failing now")
        if paused:
            parts.append(f"{paused} paused {'itself' if paused == 1 else 'themselves'}")
        parts.append(plural(firings, "firing"))
        if firings:
            parts.append(f"{ffailed} failed ({pct(ffailed, firings)}%)")
        lines += ["", "## Routines", "- " + "; ".join(parts)]
        for sch in failing_routines(schedules):
            label = sch.get("label") or sch.get("schedule_id") or "routine"
            status = sch.get("last_status") or "?"
            exit_code = sch.get("last_exit_code")
            tail = f" (exit {exit_code})" if exit_code not in (None, 0) else ""
            lines.append(
                f"- {label}: {plural(sch.get('runs') or 0, 'firing')}, {plural(sch.get('failures') or 0, 'failure')}, "
                f"last run {status}{tail}"
            )

    # Connections
    conns = s.get("connections") or 0
    uses = s.get("connection_uses") or 0
    if conns or uses:
        refused = s.get("connection_refused") or 0
        line = f"- {plural(uses, 'use')} across {plural(conns, 'connection')}"
        if refused:
            line += f"; {refused} refused"
        lines += ["", "## Connections", line]

    # Files and messages
    files = s.get("files_published") or 0
    msgs = s.get("messages_posted") or 0
    if files or msgs:
        lines += ["", "## Files and messages", f"- {plural(files, 'file')} published; {plural(msgs, 'message')} posted"]

    # Waiting on the owner
    pending = s.get("pending_requests") or 0
    waiting_long = s.get("waiting_long") or 0
    if pending or waiting_long:
        lines += [
            "",
            "## Waiting on the owner",
            f"- {plural(pending, 'pending request')}; {waiting_long} waiting longer than a week",
        ]

    # Recommendations
    lines += ["", "## Recommendations"]
    for rec in recommendations(s, n_days, schedules, runs_by_sid):
        lines.append(f"- {rec}")

    return "\n".join(lines) + "\n"


# -------------------------------------------------------------------- main


def collect(args: argparse.Namespace):
    summary_path = args.summary
    workspace_path = args.workspace
    schedules_path = args.schedules
    run_paths: List[str] = list(args.runs or [])
    if args.dir:
        d = args.dir
        summary_path = summary_path or os.path.join(d, "summary.json")
        wp = os.path.join(d, "workspace.json")
        workspace_path = workspace_path or (wp if os.path.exists(wp) else None)
        sp = os.path.join(d, "schedules.json")
        schedules_path = schedules_path or (sp if os.path.exists(sp) else None)
        run_paths += sorted(glob.glob(os.path.join(d, "schedule-runs-*.json")))
    if not summary_path or not os.path.exists(summary_path):
        raise SystemExit(2)
    try:
        summary = load_json(summary_path)
    except (OSError, ValueError):
        raise SystemExit(2)
    if not isinstance(summary, dict) or "sandbox_seconds" not in summary:
        raise SystemExit(2)
    workspace = load_json(workspace_path) if workspace_path else None
    schedules = load_json(schedules_path) if schedules_path else None
    if isinstance(schedules, dict):
        schedules = schedules.get("schedules") or schedules.get("items") or []
    runs_by_sid: Dict[str, List[Dict[str, Any]]] = {}
    for p in run_paths:
        base = os.path.basename(p)
        sid = base[len("schedule-runs-"):-len(".json")] if base.startswith("schedule-runs-") else base
        runs = load_json(p)
        if isinstance(runs, dict):
            runs = runs.get("runs") or runs.get("items") or []
        runs_by_sid[sid] = runs
    return summary, workspace, schedules, runs_by_sid


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Grupr agent usage report (offline, read-only).")
    ap.add_argument("--dir", help="folder with summary.json and optional workspace.json, schedules.json, schedule-runs-*.json")
    ap.add_argument("--summary")
    ap.add_argument("--workspace")
    ap.add_argument("--schedules")
    ap.add_argument("--runs", nargs="*", help="schedule-runs-<schedule_id>.json files")
    ap.add_argument("--days", type=int, help="override the window length used for averages")
    ap.add_argument("--name", help="agent name for the heading")
    args = ap.parse_args(argv)
    try:
        summary, workspace, schedules, runs_by_sid = collect(args)
    except SystemExit as e:
        sys.stderr.write("usage_report: summary.json missing or malformed\n")
        return int(e.code or 2)
    sys.stdout.write(build_report(summary, workspace, schedules, runs_by_sid, args.name, args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
