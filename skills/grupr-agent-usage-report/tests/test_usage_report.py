"""Tests for scripts/usage_report.py. Run from the skill folder:

    python -I -m unittest discover -s tests -v

Standard library only; no network; fixtures are sanitized sample responses.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import usage_report as ur  # noqa: E402

FIX = os.path.join(SKILL, "fixtures")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


class GoldenReport(unittest.TestCase):
    def test_fixture_report_matches_expected(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = ur.main(["--dir", FIX, "--name", "Reviewer's agent"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), read(os.path.join(FIX, "expected-report.md")))

    def test_envelope_is_unwrapped(self):
        summary = ur.load_json(os.path.join(FIX, "summary.json"))
        self.assertEqual(summary["sandbox_seconds"], 11520)
        self.assertNotIn("data", summary)

    def test_missing_summary_exits_2(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = ur.main(["--summary", os.path.join(FIX, "does-not-exist.json")])
        self.assertEqual(code, 2)
        self.assertIn("missing or malformed", err.getvalue())


class Formatting(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(ur.fmt_dur(0), "0 min")
        self.assertEqual(ur.fmt_dur(840), "14 min")
        self.assertEqual(ur.fmt_dur(3600), "1 h")
        self.assertEqual(ur.fmt_dur(7200), "2 h")
        self.assertEqual(ur.fmt_dur(11520), "3 h 12 min")

    def test_percent_omitted_on_zero_denominator(self):
        self.assertIsNone(ur.pct(3, 0))
        self.assertEqual(ur.pct(3, 41), 7)

    def test_window_days_from_timestamps(self):
        self.assertEqual(ur.window_days({"since": "2026-11-01T00:00:00Z", "until": "2026-11-08T00:00:00Z"}), 7)
        self.assertEqual(ur.window_days({"since": "x", "until": "y"}, fallback=30), 30)

    def test_suggested_budget_rounds_up_to_five_within_bounds(self):
        self.assertEqual(ur.suggested_budget_minutes(27.4), 45)   # 41.1 -> 45
        self.assertEqual(ur.suggested_budget_minutes(1.0), 5)     # floor
        self.assertEqual(ur.suggested_budget_minutes(2000.0), 1440)  # cap


class Rules(unittest.TestCase):
    base = {
        "sandbox_seconds": 11520, "sandbox_sessions": 9, "runs": 41, "runs_failed": 3, "runs_denied": 0,
        "firings": 56, "firings_failed": 5, "routines_active": 4, "routines_failing": 0, "routines_paused_self": 0,
        "connections": 2, "connection_uses": 12, "connection_refused": 0, "pending_requests": 0, "waiting_long": 0,
        "files_published": 6, "messages_posted": 23, "budget_hit": False,
    }

    def recs(self, **over):
        s = dict(self.base)
        s.update(over)
        return ur.recommendations(s, 7)

    def test_idle_agent(self):
        r = self.recs(sandbox_seconds=0, runs=0, firings=0, routines_active=0)
        self.assertEqual(r, ["The agent did nothing in this window; there is nothing to budget."])

    def test_no_budget_suggests_one(self):
        r = self.recs()
        self.assertTrue(r[0].startswith("No daily sandbox budget is set. Based on about 27 min a day, a budget of 45 min"))

    def test_budget_reached_on_a_spike(self):
        r = self.recs(budget_seconds=3600, budget_hit=True)
        self.assertIn("a spike, not a trend", r[0])
        self.assertIn("46% of the cap", r[0])

    def test_budget_reached_and_tight(self):
        r = self.recs(budget_seconds=1800, budget_hit=True)  # 27.4 min avg vs 30 min cap = 91%
        self.assertIn("The budget is tight: average use is 91% of the cap", r[0])

    def test_budget_set_but_not_hit_has_no_budget_rule(self):
        r = self.recs(budget_seconds=3600, budget_hit=False)
        self.assertFalse(any("budget" in x.lower() for x in r), r)

    def test_denied_commands_are_reported(self):
        r = self.recs(runs_denied=1)
        self.assertTrue(any(x.startswith("1 command was denied by a person") for x in r), r)

    def test_failing_commands_threshold(self):
        self.assertFalse(any("runs failed" in x for x in self.recs(runs=41, runs_failed=3)))
        self.assertTrue(any("10 of 41 runs failed (24%)" in x for x in self.recs(runs=41, runs_failed=10)))

    def test_failing_routines_name_them_with_excerpt(self):
        schedules = ur.load_json(os.path.join(FIX, "schedules.json"))
        runs = ur.load_json(os.path.join(FIX, "schedule-runs-7c1d2f30-5a7e-4d0a-9c7b-2f1e8a6b4c01.json"))
        s = dict(self.base)
        s["routines_failing"] = 1
        r = ur.recommendations(s, 7, schedules, {"7c1d2f30-5a7e-4d0a-9c7b-2f1e8a6b4c01": runs})
        line = [x for x in r if x.startswith("1 routine is failing now")][0]
        self.assertIn('nightly-site-check (last run: "HTTP 503 from https://example.com after 3 retries")', line)

    def test_refused_connection_and_owner_backlog(self):
        r = self.recs(connection_refused=2, pending_requests=1, waiting_long=1)
        self.assertTrue(any("refused 2 times" in x for x in r))
        self.assertTrue(any("1 item is waiting on the owner (1 for more than a week)" in x for x in r))

    def test_nothing_to_flag(self):
        r = self.recs(budget_seconds=7200, budget_hit=False)
        self.assertEqual(r, ["Nothing to flag."])


class Report(unittest.TestCase):
    def test_sections_omitted_when_empty(self):
        s = {"agent_id": "a", "since": "2026-11-01T00:00:00Z", "until": "2026-11-08T00:00:00Z",
             "sandbox_seconds": 0, "sandbox_sessions": 0, "runs": 0, "runs_failed": 0, "runs_denied": 0,
             "firings": 0, "firings_failed": 0, "routines_active": 0, "routines_failing": 0, "routines_paused_self": 0,
             "connections": 0, "connection_uses": 0, "connection_refused": 0, "pending_requests": 0, "waiting_long": 0,
             "files_published": 0, "messages_posted": 0, "budget_hit": False}
        text = ur.build_report(s)
        self.assertIn("## Sandbox time", text)
        self.assertIn("## Commands", text)
        for missing in ("## Routines", "## Connections", "## Files and messages", "## Waiting on the owner"):
            self.assertNotIn(missing, text)
        self.assertIn("nothing to budget", text)

    def test_no_money_words(self):
        text = read(os.path.join(FIX, "expected-report.md")).lower()
        for word in ("$", "usd", "cost", "price", "invoice"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
