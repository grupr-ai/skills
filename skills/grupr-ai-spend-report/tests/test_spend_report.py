"""Tests for scripts/spend_report.py. Run from the skill folder:

    python -I -m unittest discover -s tests -v

Standard library only. The fetch tests talk to a stub server on 127.0.0.1;
nothing leaves this machine and no real token is used.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import spend_report as sr  # noqa: E402

FIX = os.path.join(SKILL, "fixtures")
FAKE_TOKEN = "gar_" + "ab" * 32  # not a real credential


def read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def run(argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        if env is None:
            code = sr.main(argv)
        else:
            args = argparse.Namespace(out=argv["out"], days=argv.get("days", 30), since=argv.get("since"),
                                      until=argv.get("until"), people=argv.get("people", False), base=argv.get("base"))
            code = sr.cmd_fetch(args, env=env, now=datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc))
    return code, out.getvalue(), err.getvalue()


class GoldenReport(unittest.TestCase):
    def test_fixture_report_matches_expected(self):
        code, out, _ = run(["report", "--dir", FIX])
        self.assertEqual(code, 0)
        self.assertEqual(out.replace("\r\n", "\n"), read(os.path.join(FIX, "expected-report.md")).replace("\r\n", "\n"))

    def test_fixture_tables_add_up_to_the_total(self):
        total = sr.load_json(os.path.join(FIX, "summary.json"))["totals"]["cost_usd"]
        for dim in sr.BREAKDOWNS:
            rows = sr.load_json(os.path.join(FIX, "breakdown-%s.json" % dim))["rows"]
            self.assertAlmostEqual(sum(r["cost_usd"] for r in rows), total, places=2, msg=dim)
        by_model = sr.load_json(os.path.join(FIX, "summary.json"))["by_model"]
        self.assertAlmostEqual(sum(m["cost_usd"] for m in by_model), total, places=2)

    def test_missing_summary_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, err = run(["report", "--dir", d])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("summary.json is missing or malformed", err)

    def test_summary_alone_is_enough(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "summary.json"), "w", encoding="utf-8") as f:
                json.dump({"data": {"since": "2026-11-02T00:00:00Z", "until": "2026-11-09T00:00:00Z",
                                    "totals": {"calls": 1, "total_tokens": 900, "cost_usd": 0.004}, "by_model": []}}, f)
            code, out, _ = run(["report", "--dir", d, "--name", "Tiny Co"])
        self.assertEqual(code, 0)
        self.assertIn("# AI spend report: Tiny Co, 2026-11-02 to 2026-11-09 (7 days, UTC)", out)
        self.assertIn("- Spend: <$0.01 across 1 call and 900 tokens", out)
        for missing in ("## By department", "## By project", "## By model", "## By person", "## Budgets"):
            self.assertNotIn(missing, out)
        self.assertIn("- Nothing to flag.", out)


class Formatting(unittest.TestCase):
    def test_money(self):
        self.assertEqual(sr.money(0), "$0.00")
        self.assertEqual(sr.money(0.004), "<$0.01")
        self.assertEqual(sr.money(1234.5), "$1,234.50")
        self.assertEqual(sr.money(-12.3), "-$12.30")

    def test_tokens_and_counts(self):
        self.assertEqual(sr.tokens(987), "987")
        self.assertEqual(sr.tokens(12300), "12.3K")
        self.assertEqual(sr.tokens(412600000), "412.6M")
        self.assertEqual(sr.tokens(2500000000), "2.5B")
        self.assertEqual(sr.count(18420), "18,420")

    def test_share_is_none_without_a_denominator(self):
        self.assertIsNone(sr.share(5, 0))
        self.assertEqual(sr.share(881.5, 6184.37), 14)
        self.assertEqual(sr.share_text(1, 0), "n/a")

    def test_table_cells_cannot_break_the_table(self):
        self.assertEqual(sr.cell("a|b\nc"), "a/b c")
        self.assertEqual(sr.cell(""), "(blank)")

    def test_other_row_folds_the_tail(self):
        rows = [{"bucket": "d%02d" % i, "calls": 1, "cost_usd": float(20 - i)} for i in range(13)]
        table = sr.bucket_table("Department", rows, sum(r["cost_usd"] for r in rows))
        self.assertEqual(len(table), 2 + sr.TOP_N + 1)
        self.assertTrue(table[2].startswith("| d00 | $20.00 |"))
        self.assertTrue(table[-1].startswith("| Other (3 more) | $27.00 |"), table[-1])

    def test_window_days(self):
        self.assertEqual(sr.window_days({"since": "2026-10-10T00:00:00Z", "until": "2026-11-09T00:00:00Z"}), 30)
        self.assertEqual(sr.window_days({"since": "x", "until": "y"}, fallback=7), 7)


class Rules(unittest.TestCase):
    def summary(self, cost=1000.0, calls=100, models=None):
        return {"since": "2026-10-10T00:00:00Z", "until": "2026-11-09T00:00:00Z",
                "totals": {"calls": calls, "total_tokens": 1000, "cost_usd": cost},
                "by_model": models if models is not None else [
                    {"provider": "a", "model": "m1", "cost_usd": cost * 0.5, "calls": 1, "total_tokens": 1},
                    {"provider": "b", "model": "m2", "cost_usd": cost * 0.5, "calls": 1, "total_tokens": 1}]}

    def bd(self, *rows, truncated=False):
        return {"rows": [{"bucket": b, "calls": 1, "cost_usd": c} for b, c in rows], "truncated": truncated}

    def key(self, name, spend, cap=None, raise_=0.0, status="active", dept=""):
        eff = None if cap is None else cap + raise_
        return {"name": name, "department": dept, "status": status, "monthly_cap_usd": cap,
                "approved_raise_usd": raise_, "effective_cap_usd": eff, "spend_mtd_usd": spend}

    def recs(self, summary=None, breakdowns=None, budgets=None):
        return sr.recommendations(summary or self.summary(), breakdowns or {}, budgets)

    def test_nothing_to_flag(self):
        self.assertEqual(self.recs(), ["Nothing to flag."])

    def test_idle_window(self):
        r = self.recs(self.summary(cost=0, calls=0, models=[]))
        self.assertEqual(r, ["No usage was recorded in this window; there is nothing to attribute."])

    def test_unassigned_department_threshold(self):
        under = self.recs(breakdowns={"department": self.bd(("Eng", 910), ("(unassigned)", 90))})
        over = self.recs(breakdowns={"department": self.bd(("Eng", 900), ("(unassigned)", 100))})
        self.assertFalse(any("no department" in x for x in under))
        self.assertTrue(any(x.startswith("10% of spend ($100.00) has no department") for x in over), over)

    def test_no_project_needs_real_projects_to_matter(self):
        only_none = self.recs(breakdowns={"project": self.bd(("(no project)", 1000))})
        mixed = self.recs(breakdowns={"project": self.bd(("(no project)", 400), ("Checkout", 600))})
        small = self.recs(breakdowns={"project": self.bd(("(no project)", 200), ("Checkout", 800))})
        self.assertFalse(any("project" in x for x in only_none), only_none)
        self.assertTrue(any(x.startswith("40% of spend ($400.00) is not tied to a project") for x in mixed), mixed)
        self.assertFalse(any("project" in x for x in small), small)

    def test_cap_rules_use_the_effective_cap_and_skip_revoked_keys(self):
        budgets = {"keys": [
            self.key("at-cap", 100, cap=100, dept="Ops"),
            self.key("raised", 110, cap=100, raise_=50),          # 73% of 150: fine
            self.key("near", 80, cap=100),
            self.key("fine", 79.9, cap=100),
            self.key("gone", 500, cap=100, status="revoked"),
            self.key("open", 12.5),
            self.key("unused-open", 0),
        ], "pending_overage_requests": 2}
        r = self.recs(budgets=budgets)
        self.assertIn("1 key is at or over this month's cap, so the gateway answers 402 budget_exceeded: "
                      "at-cap (Ops) at 100%. Raise the cap or decide the overage request.", r)
        self.assertIn("1 key has used 80% or more of this month's cap and will be refused at 100%: near at 80%.", r)
        self.assertIn("1 key has no monthly cap and spent $12.50 this month. A cap is the only hard stop on a key.", r)
        self.assertIn("2 overage requests are waiting on an admin or finance approver.", r)
        joined = " ".join(r)
        for absent in ("raised", "fine", "gone", "unused-open"):
            self.assertNotIn(absent, joined)

    def test_budget_rules_fire_in_an_idle_window(self):
        r = self.recs(self.summary(cost=0, calls=0, models=[]), budgets={"keys": [self.key("k", 99, cap=100)]})
        self.assertEqual(len(r), 2)
        self.assertIn("80% or more", r[1])

    def test_model_concentration(self):
        models = [{"provider": "anthropic", "model": "big", "cost_usd": 600}, {"provider": "openai", "model": "small", "cost_usd": 400}]
        r = self.recs(self.summary(models=models))
        self.assertTrue(any(x.startswith("60% of spend is one model (anthropic/big).") for x in r), r)
        models[0]["cost_usd"], models[1]["cost_usd"] = 590, 410
        self.assertEqual(self.recs(self.summary(models=models)), ["Nothing to flag."])

    def test_non_gateway_share(self):
        r = self.recs(breakdowns={"source": self.bd(("gateway", 800), ("otel", 150), ("provider_api", 50))})
        self.assertTrue(any(x.startswith("20% of spend ($200.00) was captured from telemetry or provider reports") for x in r), r)
        r = self.recs(breakdowns={"source": self.bd(("gateway", 810), ("otel", 190))})
        self.assertEqual(r, ["Nothing to flag."])

    def test_truncated_breakdown_is_reported(self):
        r = self.recs(breakdowns={"department": self.bd(("Eng", 1000), truncated=True)})
        self.assertIn("The department breakdown hit the 200-bucket limit; its table covers the 200 largest buckets only.", r)

    def test_no_savings_or_forecast_language(self):
        text = read(os.path.join(FIX, "expected-report.md")).lower()
        for word in ("save", "saving", "forecast", "projected", "will cost", "roi"):
            self.assertNotIn(word, text)


class Report(unittest.TestCase):
    def test_people_section_only_when_present_and_carries_a_warning(self):
        summary = sr.load_json(os.path.join(FIX, "summary.json"))
        without = sr.build_report(summary)
        people = {"rows": [{"bucket": "ana@example.com", "calls": 10, "cost_usd": 12.0}], "truncated": False}
        with_people = sr.build_report(summary, breakdowns={"user": people})
        self.assertNotIn("## By person", without)
        self.assertIn("## By person", with_people)
        self.assertIn("personal data", with_people)

    def test_budget_section_with_no_keys(self):
        summary = sr.load_json(os.path.join(FIX, "summary.json"))
        text = sr.build_report(summary, budgets={"as_of": "2026-11-09T12:00:00Z", "keys": [], "pending_overage_requests": 0})
        self.assertIn("## Budgets this month (as of 2026-11-09)\n- No active virtual keys\n", text)

    def test_title_falls_back_without_info(self):
        summary = sr.load_json(os.path.join(FIX, "summary.json"))
        self.assertTrue(sr.build_report(summary).startswith("# AI spend report: your organization, 2026-10-10 to 2026-11-09"))


# ------------------------------------------------------------------- fetch


class StubAPI(BaseHTTPRequestHandler):
    """Serves the fixtures the way the read API would, and records requests."""

    seen = []
    mode = "ok"
    allow_people = False

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        StubAPI.seen.append((self.path, dict(self.headers)))
        if self.headers.get("Authorization") != "Bearer " + FAKE_TOKEN:
            return self._send(401, {"errors": [{"code": "unauthorized", "message": "Invalid, expired or revoked read token"}]})
        if StubAPI.mode == "ratelimit":
            return self._send(429, {"errors": [{"code": "rate_limited", "message": "Too many requests; retry after 17s", "retry_after_seconds": 17}]})
        if StubAPI.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.end_headers()
            return
        path, _, query = self.path.partition("?")
        if path == "/api/v1/analytics":
            body = json.loads(read(os.path.join(FIX, "info.json")))
            body["data"]["token"]["allow_people"] = StubAPI.allow_people
            return self._send(200, body)
        if path == "/api/v1/analytics/usage/summary":
            return self._file("summary.json")
        if path == "/api/v1/analytics/usage/breakdown":
            dim = dict(p.split("=", 1) for p in query.split("&"))["dimension"]
            if dim == "user":
                return self._send(200, {"data": {"dimension": "user", "rows": [{"bucket": "ana@example.com", "calls": 3, "cost_usd": 1.5}], "truncated": False}})
            return self._file("breakdown-%s.json" % dim)
        if path == "/api/v1/analytics/budgets":
            return self._file("budgets.json")
        self._send(404, {"errors": [{"code": "not_found", "message": "no such route"}]})

    def _file(self, name):
        raw = read(os.path.join(FIX, name)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send(self, status, obj):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class Fetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), StubAPI)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        StubAPI.seen, StubAPI.mode, StubAPI.allow_people = [], "ok", False
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "export")

    def fetch(self, env=None, **kw):
        return run(dict(out=self.out, base=self.base, **kw), env={sr.TOKEN_ENV: FAKE_TOKEN} if env is None else env)

    def test_fetch_then_report_reproduces_the_golden_file(self):
        code, out, err = self.fetch()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(sorted(os.listdir(self.out)), [
            "breakdown-department.json", "breakdown-project.json", "breakdown-source.json",
            "budgets.json", "info.json", "summary.json"])
        code, report, _ = run(["report", "--dir", self.out])
        self.assertEqual(code, 0)
        self.assertEqual(report.replace("\r\n", "\n"), read(os.path.join(FIX, "expected-report.md")).replace("\r\n", "\n"))

    def test_every_request_is_a_get_with_the_token_in_the_header_only(self):
        self.fetch()
        self.assertEqual(len(StubAPI.seen), 6)
        for path, headers in StubAPI.seen:
            self.assertEqual(headers.get("Authorization"), "Bearer " + FAKE_TOKEN)
            self.assertTrue(headers.get("User-Agent", "").startswith("grupr-ai-spend-report/"))
            self.assertNotIn(FAKE_TOKEN, path)
            self.assertNotIn("gar_", path)
        windowed = [p for p, _ in StubAPI.seen if "usage/" in p]
        self.assertEqual(len(windowed), 4)
        for p in windowed:
            self.assertIn("since=2026-10-10T12%3A00%3A00Z", p)
            self.assertIn("until=2026-11-09T12%3A00%3A00Z", p)

    def test_the_token_is_never_printed_or_written(self):
        code, out, err = self.fetch()
        self.assertEqual(code, 0)
        self.assertNotIn(FAKE_TOKEN, out + err)
        self.assertNotIn("gar_", out + err)
        for name in os.listdir(self.out):
            self.assertNotIn(FAKE_TOKEN, read(os.path.join(self.out, name)), name)

    def test_missing_or_wrong_kind_of_token(self):
        for env, needle in (({}, "is not set"), ({sr.TOKEN_ENV: "gat_agenttoken"}, "does not hold an Analytics read token"),
                            ({sr.TOKEN_ENV: "gvk_virtualkey"}, "does not hold an Analytics read token")):
            code, out, err = self.fetch(env=env)
            self.assertEqual(code, 2)
            self.assertIn(needle, err)
            self.assertNotIn("agenttoken", err)
            self.assertNotIn("virtualkey", err)
        self.assertEqual(StubAPI.seen, [])

    def test_the_token_is_not_sent_to_other_hosts(self):
        for base in ("https://example.com", "http://api.grupr.ai", "https://api.grupr.ai.evil.test", "https://evil.test/api.grupr.ai"):
            code, _, err = run(dict(out=self.out, base=base), env={sr.TOKEN_ENV: FAKE_TOKEN})
            self.assertEqual(code, 2, base)
            self.assertIn("refusing to send the read token", err)
        self.assertEqual(sr.check_base("https://api.grupr.ai/"), "https://api.grupr.ai")
        self.assertEqual(StubAPI.seen, [])

    def test_rejected_token(self):
        code, out, err = self.fetch(env={sr.TOKEN_ENV: "gar_" + "00" * 32})
        self.assertEqual(code, 3)
        self.assertIn("401 unauthorized", err)
        self.assertIn("revoked read token. The token is wrong, expired or revoked; an org admin can create a new one.", err)
        self.assertNotIn("gar_", err)

    def test_rate_limit_says_how_long_to_wait(self):
        StubAPI.mode = "ratelimit"
        code, _, err = self.fetch()
        self.assertEqual(code, 3)
        self.assertIn("429 rate_limited", err)
        self.assertIn("Wait 17 seconds", err)

    def test_redirects_are_not_followed(self):
        StubAPI.mode = "redirect"
        code, _, err = self.fetch()
        self.assertEqual(code, 3)
        self.assertEqual(len(StubAPI.seen), 1)
        self.assertIn("302", err)

    def test_people_only_when_asked_and_allowed(self):
        self.fetch()
        self.assertFalse(any("dimension=user" in p for p, _ in StubAPI.seen))
        StubAPI.seen = []
        code, out, _ = self.fetch(people=True)
        self.assertEqual(code, 0)
        self.assertIn("skipped breakdown-user.json", out)
        self.assertFalse(any("dimension=user" in p for p, _ in StubAPI.seen))
        StubAPI.seen, StubAPI.allow_people = [], True
        code, out, _ = self.fetch(people=True)
        self.assertEqual(code, 0)
        self.assertTrue(any("dimension=user" in p for p, _ in StubAPI.seen))
        self.assertIn("## By person", run(["report", "--dir", self.out])[1])

    def test_window_arguments(self):
        for kw, needle in ((dict(days=0), "--days must be between 1 and 366"), (dict(days=400), "--days must be between 1 and 366"),
                           (dict(since="2026-10-01"), "give both --since and --until"), (dict(since="10/01/2026", until="2026-11-01"), "does not match format")):
            code, _, err = self.fetch(**kw)
            self.assertEqual(code, 2, kw)
            self.assertIn(needle, err)
        self.assertEqual(StubAPI.seen, [])
        self.fetch(since="2026-10-01", until="2026-11-01")
        self.assertTrue(any("since=2026-10-01&until=2026-11-01" in p for p, _ in StubAPI.seen))


if __name__ == "__main__":
    unittest.main()
