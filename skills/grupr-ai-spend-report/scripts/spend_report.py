#!/usr/bin/env python3
"""Grupr AI spend report.

Two steps, both read-only:

  fetch   GET the Grupr Analytics read API with a read token taken from the
          GRUPR_ANALYTICS_TOKEN environment variable, and save the JSON
          responses to a folder. This is the only step that uses the network.
  report  Build a Markdown spend report from that folder. No network.

    python -I spend_report.py fetch --out ./spend-export [--days 30] [--people]
    python -I spend_report.py report --dir ./spend-export [--name "Org name"]

Standard library only. The token is read from the environment, sent only in
the Authorization header, only to https://api.grupr.ai, and is never printed
or written to disk. The API it calls has no write endpoints.

Exit codes: 0 done; 2 bad input or missing data; 3 the API refused a request.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

VERSION = "0.1.0"
USER_AGENT = "grupr-ai-spend-report/" + VERSION
DEFAULT_BASE = "https://api.grupr.ai"
TOKEN_ENV = "GRUPR_ANALYTICS_TOKEN"
TOKEN_PREFIX = "gar_"
BREAKDOWNS = ("department", "project", "source")
TOP_N = 10
NEAR_CAP_PCT = 80.0
# Below this much spend in the window, "X% of spend is ..." says nothing useful:
# the share-based recommendations are skipped and the report says why.
MIN_SPEND_FOR_SHARE_RULES = 10.0

SOURCE_LABELS = {
    "gateway": "gateway",
    "otel": "telemetry",
    "provider_api": "provider-reported",
    "agent": "agent-reported",
}

# ----------------------------------------------------------------- loading


def load_json(path: str) -> Any:
    """Load a saved response, unwrapping the API's {"data": ...} envelope."""
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    if isinstance(obj, dict) and "data" in obj and isinstance(obj["data"], (dict, list)):
        return obj["data"]
    return obj


def load_optional(path: str) -> Any:
    if not os.path.isfile(path):
        return None
    try:
        return load_json(path)
    except (OSError, ValueError):
        return None


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


def window_days(summary: Dict[str, Any], fallback: int = 30) -> int:
    since, until = parse_ts(summary.get("since")), parse_ts(summary.get("until"))
    if since and until and until > since:
        return max(1, round((until - since).total_seconds() / 86400))
    return fallback


def fnum(value: Any) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0


# -------------------------------------------------------------- formatting


def money(v: float) -> str:
    if 0 < abs(v) < 0.005:
        return "<$0.01"
    sign = "-" if v < 0 else ""
    return "%s$%s" % (sign, format(abs(v), ",.2f"))


def count(n: Any) -> str:
    return format(int(fnum(n)), ",d")


def tokens(n: Any) -> str:
    v = fnum(n)
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= size:
            return "%.1f%s" % (v / size, suffix)
    return "%d" % v


def share(part: float, whole: float) -> Optional[int]:
    """Whole-number percentage, or None when there is nothing to divide by."""
    if whole <= 0:
        return None
    return int(round(100.0 * part / whole))


def share_text(part: float, whole: float) -> str:
    p = share(part, whole)
    if p is None:
        return "n/a"
    if p == 0 and part > 0:
        return "<1%"  # something was spent; do not round it to nothing
    return "%d%%" % p


def plural(n: int, one: str, many: Optional[str] = None) -> str:
    return "%d %s" % (n, one if n == 1 else (many or one + "s"))


def cell(text: Any) -> str:
    """A value made safe for a Markdown table cell."""
    return str(text).replace("|", "/").replace("\n", " ").strip() or "(blank)"


# ------------------------------------------------------------------ tables


def bucket_rows(breakdown: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = (breakdown or {}).get("rows") or []
    return [r for r in rows if isinstance(r, dict)]


def bucket_cost(breakdown: Optional[Dict[str, Any]], bucket: str) -> float:
    return sum(fnum(r.get("cost_usd")) for r in bucket_rows(breakdown) if r.get("bucket") == bucket)


def bucket_table(title: str, rows: List[Dict[str, Any]], total: float) -> List[str]:
    """Top-N buckets by spend, the rest folded into one "Other" row."""
    ordered = sorted(rows, key=lambda r: -fnum(r.get("cost_usd")))
    out = ["| %s | Spend | Share | Calls |" % title, "|---|---:|---:|---:|"]
    for r in ordered[:TOP_N]:
        c = fnum(r.get("cost_usd"))
        out.append("| %s | %s | %s | %s |" % (cell(r.get("bucket")), money(c), share_text(c, total), count(r.get("calls"))))
    rest = ordered[TOP_N:]
    if rest:
        c = sum(fnum(r.get("cost_usd")) for r in rest)
        calls = sum(fnum(r.get("calls")) for r in rest)
        out.append("| Other (%d more) | %s | %s | %s |" % (len(rest), money(c), share_text(c, total), count(calls)))
    return out


def model_table(by_model: List[Dict[str, Any]], total: float) -> List[str]:
    ordered = sorted(by_model, key=lambda r: -fnum(r.get("cost_usd")))
    out = ["| Model | Provider | Spend | Share | Calls | Tokens |", "|---|---|---:|---:|---:|---:|"]
    for r in ordered[:TOP_N]:
        c = fnum(r.get("cost_usd"))
        out.append("| %s | %s | %s | %s | %s | %s |" % (
            cell(r.get("model")), cell(r.get("provider")), money(c), share_text(c, total),
            count(r.get("calls")), tokens(r.get("total_tokens"))))
    rest = ordered[TOP_N:]
    if rest:
        c = sum(fnum(r.get("cost_usd")) for r in rest)
        out.append("| Other (%d more) |  | %s | %s | %s | %s |" % (
            len(rest), money(c), share_text(c, total),
            count(sum(fnum(r.get("calls")) for r in rest)), tokens(sum(fnum(r.get("total_tokens")) for r in rest))))
    return out


# ----------------------------------------------------------------- budgets


def budget_keys(budgets: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [k for k in ((budgets or {}).get("keys") or []) if isinstance(k, dict)]


def key_percent(k: Dict[str, Any]) -> Optional[float]:
    """Share of the effective cap used, recomputed so the report does not
    depend on a rounded field. None when the key has no cap."""
    cap = k.get("effective_cap_usd")
    if cap is None:
        cap = k.get("monthly_cap_usd")
    if cap is None:
        return None
    cap = fnum(cap)
    if cap <= 0:
        return None
    return 100.0 * fnum(k.get("spend_mtd_usd")) / cap


def key_label(k: Dict[str, Any]) -> str:
    name = str(k.get("name") or "(unnamed key)")
    dept = str(k.get("department") or "").strip()
    return "%s (%s)" % (name, dept) if dept else name


def key_cap(k: Dict[str, Any]) -> float:
    cap = k.get("effective_cap_usd")
    if cap is None:
        cap = k.get("monthly_cap_usd")
    return fnum(cap)


def classify_keys(budgets: Optional[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    active = [k for k in budget_keys(budgets) if k.get("status", "active") == "active"]
    capped = [k for k in active if key_percent(k) is not None]
    over = sorted([k for k in capped if key_percent(k) >= 100.0], key=lambda k: -key_percent(k))
    near = sorted([k for k in capped if NEAR_CAP_PCT <= key_percent(k) < 100.0], key=lambda k: -key_percent(k))
    uncapped = [k for k in active if key_percent(k) is None and fnum(k.get("spend_mtd_usd")) > 0]
    return {"active": active, "capped": capped, "over": over, "near": near, "uncapped": uncapped}


# --------------------------------------------------------- recommendations


def recommendations(summary: Dict[str, Any], breakdowns: Dict[str, Optional[Dict[str, Any]]],
                    budgets: Optional[Dict[str, Any]]) -> List[str]:
    """The fixed rule set in references/report-rules.md, in order."""
    out: List[str] = []
    totals = summary.get("totals") or {}
    total = fnum(totals.get("cost_usd"))
    idle = total <= 0 and fnum(totals.get("calls")) <= 0
    material = total >= MIN_SPEND_FOR_SHARE_RULES

    if idle:
        out.append("No usage was recorded in this window; there is nothing to attribute.")
    else:
        if not material:
            out.append(
                "Spend in this window is under %s, too little for share-based recommendations (department, "
                "project, model, capture source) to mean anything; they are skipped." % money(MIN_SPEND_FOR_SHARE_RULES))
        dept = breakdowns.get("department")
        unassigned = bucket_cost(dept, "(unassigned)")
        if material and unassigned / total >= 0.10:
            out.append(
                "%d%% of spend (%s) has no department. Label the virtual keys with a department, or import "
                "the directory, so it rolls up to a team." % (share(unassigned, total), money(unassigned)))

        proj = breakdowns.get("project")
        no_project = bucket_cost(proj, "(no project)")
        has_projects = any(r.get("bucket") != "(no project)" for r in bucket_rows(proj))
        if material and has_projects and no_project / total >= 0.25:
            out.append(
                "%d%% of spend (%s) is not tied to a project. Bind keys to a project, or map repositories to "
                "one, if project-level numbers matter to you." % (share(no_project, total), money(no_project)))

    keys = classify_keys(budgets)
    if keys["over"]:
        out.append(
            "%s at or over this month's cap, so the gateway answers 402 budget_exceeded: %s. "
            "Raise the cap or decide the overage request." % (
                plural(len(keys["over"]), "key is", "keys are"),
                "; ".join("%s at %d%%" % (key_label(k), round(key_percent(k))) for k in keys["over"][:TOP_N])))
    if keys["near"]:
        out.append(
            "%s used 80%% or more of this month's cap and will be refused at 100%%: %s." % (
                plural(len(keys["near"]), "key has", "keys have"),
                "; ".join("%s at %d%%" % (key_label(k), round(key_percent(k))) for k in keys["near"][:TOP_N])))
    if keys["uncapped"]:
        spent = sum(fnum(k.get("spend_mtd_usd")) for k in keys["uncapped"])
        out.append(
            "%s no monthly cap and spent %s this month. A cap is the only hard stop on a key." % (
                plural(len(keys["uncapped"]), "key has", "keys have"), money(spent)))
    pending = int(fnum((budgets or {}).get("pending_overage_requests")))
    if pending > 0:
        out.append("%s waiting on an admin or finance approver." % plural(
            pending, "overage request is", "overage requests are"))

    if not idle:
        by_model = [m for m in (summary.get("by_model") or []) if isinstance(m, dict)]
        if by_model and material:
            top = max(by_model, key=lambda m: fnum(m.get("cost_usd")))
            if fnum(top.get("cost_usd")) / total >= 0.60:
                out.append(
                    "%d%% of spend is one model (%s/%s). If part of that work fits a cheaper model, an "
                    "allowed-models list on the key enforces the choice." % (
                        share(fnum(top.get("cost_usd")), total), top.get("provider"), top.get("model")))

        src = breakdowns.get("source")
        non_gateway = sum(fnum(r.get("cost_usd")) for r in bucket_rows(src) if r.get("bucket") != "gateway")
        if material and non_gateway / total >= 0.20:
            out.append(
                "%d%% of spend (%s) was captured from telemetry or provider reports, not the gateway. Monthly "
                "caps do not apply to it." % (share(non_gateway, total), money(non_gateway)))

    for dim in sorted(breakdowns):
        if (breakdowns[dim] or {}).get("truncated"):
            out.append("The %s breakdown hit the 200-bucket limit; its table covers the 200 largest buckets only." % dim)

    return out or ["Nothing to flag."]


# ------------------------------------------------------------------ report


def build_report(summary: Dict[str, Any], info: Optional[Dict[str, Any]] = None,
                 breakdowns: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
                 budgets: Optional[Dict[str, Any]] = None, org_name: Optional[str] = None) -> str:
    breakdowns = breakdowns or {}
    days = window_days(summary)
    since, until = parse_ts(summary.get("since")), parse_ts(summary.get("until"))
    name = org_name or ((info or {}).get("org") or {}).get("name") or "your organization"
    span = "%s to %s" % (since.date().isoformat(), until.date().isoformat()) if since and until else "last %d days" % days

    totals = summary.get("totals") or {}
    total = fnum(totals.get("cost_usd"))
    calls = fnum(totals.get("calls"))
    lines = ["# AI spend report: %s, %s (%s, UTC)" % (name, span, plural(days, "day")), "", "## Total"]

    if total <= 0 and calls <= 0:
        lines.append("- No usage recorded in this window")
    else:
        per_day = total / days
        lines.append("- Spend: %s across %s %s and %s tokens (%s a day)" % (
            money(total), count(calls), "call" if int(calls) == 1 else "calls",
            tokens(totals.get("total_tokens")),
            "about " + money(per_day) if per_day >= 0.005 else "under $0.01"))
        src_rows = sorted(bucket_rows(breakdowns.get("source")), key=lambda r: -fnum(r.get("cost_usd")))
        if src_rows:
            lines.append("- By capture source: " + "; ".join(
                "%s %s (%s)" % (SOURCE_LABELS.get(str(r.get("bucket")), cell(r.get("bucket"))),
                                money(fnum(r.get("cost_usd"))), share_text(fnum(r.get("cost_usd")), total))
                for r in src_rows))

        for dim, title in (("department", "Department"), ("project", "Project")):
            rows = bucket_rows(breakdowns.get(dim))
            if rows:
                lines += ["", "## By %s" % dim] + bucket_table(title, rows, total)

        by_model = [m for m in (summary.get("by_model") or []) if isinstance(m, dict)]
        if by_model:
            lines += ["", "## By model"] + model_table(by_model, total)

        people = bucket_rows(breakdowns.get("user"))
        if people:
            lines += ["", "## By person", "Per-person usage is personal data. Share this section only with people who need it.", ""]
            lines += bucket_table("Person", people, total)

    if budgets is not None:
        keys = classify_keys(budgets)
        as_of = parse_ts(budgets.get("as_of"))
        lines += ["", "## Budgets this month" + (" (as of %s)" % as_of.date().isoformat() if as_of else "")]
        if not keys["active"]:
            lines.append("- No active virtual keys")
        else:
            cap_total = sum(key_cap(k) for k in keys["capped"])
            cap_spend = sum(fnum(k.get("spend_mtd_usd")) for k in keys["capped"])
            head = "- %s; %s a monthly cap" % (
                plural(len(keys["active"]), "active key"), plural(len(keys["capped"]), "has", "have"))
            if keys["capped"]:
                head += "; %s of %s capped budget used (%s)" % (money(cap_spend), money(cap_total), share_text(cap_spend, cap_total))
            lines.append(head)
            for k in (keys["over"] + keys["near"])[:TOP_N]:
                lines.append("- %s: %s of %s (%d%%)" % (
                    key_label(k), money(fnum(k.get("spend_mtd_usd"))), money(key_cap(k)), round(key_percent(k))))
            if keys["uncapped"]:
                lines.append("- %s without a cap spent %s" % (
                    plural(len(keys["uncapped"]), "key"), money(sum(fnum(k.get("spend_mtd_usd")) for k in keys["uncapped"]))))
            lines.append("- Budget spend counts gateway traffic only, the basis caps are enforced on")
        pending = int(fnum(budgets.get("pending_overage_requests")))
        if pending > 0:
            lines.append("- %s waiting on an approver" % plural(pending, "overage request"))

    lines += ["", "## Recommendations"]
    lines += ["- " + r for r in recommendations(summary, breakdowns, budgets)]
    return "\n".join(lines) + "\n"


def cmd_report(args: argparse.Namespace) -> int:
    d = args.dir
    try:
        summary = load_json(os.path.join(d, "summary.json"))
    except (OSError, ValueError) as e:
        print("error: summary.json is missing or malformed in %s (%s)" % (d, e.__class__.__name__), file=sys.stderr)
        return 2
    if not isinstance(summary, dict) or "totals" not in summary:
        print("error: summary.json is not a usage summary (no totals)", file=sys.stderr)
        return 2
    breakdowns = {dim: load_optional(os.path.join(d, "breakdown-%s.json" % dim)) for dim in BREAKDOWNS + ("user",)}
    breakdowns = {k: v for k, v in breakdowns.items() if isinstance(v, dict)}
    info = load_optional(os.path.join(d, "info.json"))
    budgets = load_optional(os.path.join(d, "budgets.json"))
    sys.stdout.write(build_report(
        summary, info if isinstance(info, dict) else None, breakdowns,
        budgets if isinstance(budgets, dict) else None, args.name))
    return 0


# ------------------------------------------------------------------- fetch


class ApiRefused(Exception):
    def __init__(self, path: str, status: int, code: str, message: str, retry_after: Optional[int] = None):
        super().__init__("%s -> %d %s" % (path, status, code))
        self.path, self.status, self.code, self.message, self.retry_after = path, status, code, message, retry_after


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: it would carry the Authorization header to
    wherever the redirect points."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def check_base(base: str) -> str:
    """The token goes to api.grupr.ai over https, or to this machine (tests).
    Anywhere else is refused before a request is made."""
    u = urllib.parse.urlsplit(base)
    host = (u.hostname or "").lower()
    local = host in ("localhost", "127.0.0.1", "::1")
    if u.scheme == "https" and host == "api.grupr.ai":
        return base.rstrip("/")
    if local and u.scheme in ("http", "https"):
        return base.rstrip("/")
    raise ValueError("refusing to send the read token to %r; the API is %s" % (host or base, DEFAULT_BASE))


def read_token(env: Dict[str, str]) -> str:
    token = (env.get(TOKEN_ENV) or "").strip()
    if not token:
        raise ValueError("%s is not set. An org admin creates a read token under Analytics, API read tokens." % TOKEN_ENV)
    if not token.startswith(TOKEN_PREFIX):
        raise ValueError("%s does not hold an Analytics read token (they start with %s)." % (TOKEN_ENV, TOKEN_PREFIX))
    return token


def api_get(base: str, path: str, token: str, query: Optional[Dict[str, str]] = None, timeout: float = 30.0) -> bytes:
    url = base + path + ("?" + urllib.parse.urlencode(query) if query else "")
    req = urllib.request.Request(url, method="GET", headers={
        "Authorization": "Bearer " + token, "User-Agent": USER_AGENT, "Accept": "application/json"})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        code, message, retry = "http_%d" % e.code, "", None
        try:
            err = (json.loads(e.read().decode("utf-8", "replace")).get("errors") or [{}])[0]
            code = str(err.get("code") or code)
            message = str(err.get("message") or "")
            retry = err.get("retry_after_seconds")
        except (ValueError, AttributeError, IndexError):
            pass
        raise ApiRefused(path, e.code, code, message, retry if isinstance(retry, int) else None) from None


def fetch_window(args: argparse.Namespace, now: datetime) -> Tuple[str, str]:
    if args.since or args.until:
        if not (args.since and args.until):
            raise ValueError("give both --since and --until (YYYY-MM-DD), or neither")
        for v in (args.since, args.until):
            datetime.strptime(v, "%Y-%m-%d")
        return args.since, args.until
    if not 1 <= args.days <= 366:
        raise ValueError("--days must be between 1 and 366")
    until = now.astimezone(timezone.utc).replace(microsecond=0)
    since = until - timedelta(days=args.days)
    return since.strftime("%Y-%m-%dT%H:%M:%SZ"), until.strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_fetch(args: argparse.Namespace, env: Optional[Dict[str, str]] = None, now: Optional[datetime] = None) -> int:
    env = dict(os.environ) if env is None else env
    try:
        base = check_base(args.base or env.get("GRUPR_API_BASE") or DEFAULT_BASE)
        token = read_token(env)
        since, until = fetch_window(args, now or datetime.now(timezone.utc))
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2

    window = {"since": since, "until": until}
    plan: List[Tuple[str, str, Optional[Dict[str, str]]]] = [
        ("info.json", "/api/v1/analytics", None),
        ("summary.json", "/api/v1/analytics/usage/summary", window),
    ]
    for dim in BREAKDOWNS:
        plan.append(("breakdown-%s.json" % dim, "/api/v1/analytics/usage/breakdown", dict(window, dimension=dim)))
    plan.append(("budgets.json", "/api/v1/analytics/budgets", None))

    os.makedirs(args.out, exist_ok=True)
    allow_people = False
    try:
        for i, (fname, path, query) in enumerate(plan):
            body = api_get(base, path, token, query)
            with open(os.path.join(args.out, fname), "wb") as f:
                f.write(body)
            print("saved %s (%d bytes)" % (fname, len(body)))
            if i == 0:
                try:
                    allow_people = bool(json.loads(body)["data"]["token"]["allow_people"])
                except (ValueError, KeyError, TypeError):
                    allow_people = False
        if args.people:
            if not allow_people:
                print("skipped breakdown-user.json: this read token cannot read per-person usage")
            else:
                body = api_get(base, "/api/v1/analytics/usage/breakdown", token, dict(window, dimension="user"))
                with open(os.path.join(args.out, "breakdown-user.json"), "wb") as f:
                    f.write(body)
                print("saved breakdown-user.json (%d bytes)" % len(body))
    except ApiRefused as e:
        hint = ""
        if e.status == 401:
            hint = " The token is wrong, expired or revoked; an org admin can create a new one."
        elif e.status == 429 and e.retry_after:
            hint = " Wait %d seconds and run it again." % e.retry_after
        detail = e.message.rstrip()
        if detail and detail[-1] not in ".!?":
            detail += "."
        print("error: GET %s was refused: %d %s. %s%s" % (e.path, e.status, e.code, detail, hint), file=sys.stderr)
        return 3
    except (urllib.error.URLError, OSError) as e:
        print("error: could not reach the API (%s)" % e.__class__.__name__, file=sys.stderr)
        return 3
    print("done. The files hold your organization's spend: keep the folder private and do not commit it.")
    return 0


# --------------------------------------------------------------------- cli


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Grupr AI spend report (read-only).")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="save the Analytics read API responses to a folder")
    f.add_argument("--out", required=True, help="folder to write the JSON files to")
    f.add_argument("--days", type=int, default=30, help="window length, 1 to 366 (default 30)")
    f.add_argument("--since", help="window start, YYYY-MM-DD (UTC); use with --until")
    f.add_argument("--until", help="window end, YYYY-MM-DD (UTC, exclusive); use with --since")
    f.add_argument("--people", action="store_true", help="also fetch per-person usage, if the token allows it")
    f.add_argument("--base", help=argparse.SUPPRESS)

    r = sub.add_parser("report", help="print the Markdown report from a fetched folder")
    r.add_argument("--dir", required=True, help="folder holding summary.json and the other files")
    r.add_argument("--name", help="organization name for the title (default: from info.json)")

    args = p.parse_args(argv)
    return cmd_fetch(args) if args.cmd == "fetch" else cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
