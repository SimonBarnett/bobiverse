#!/usr/bin/env python3
"""FR #9878: Jeeves outbox shop-wire assign when ear !assign / cmd-trace is mute.

Append UTF-8 no-BOM lines to chair/Jeeves outbox (BOB_CHAIR_OUTBOX or
``~/.jeeves/outbox.txt``):

  PRIVMSG #<machine> :<nick>: MRB|FIX|FR owner/repo#N <url>
  PRIVMSG #bobiverse :assign: sent <nick>: TASK owner/repo#N <url>

Prefer ear-relay !assign (FR #9461) when cmd-trace is fresh. Live mute
incidents that must write the walrus chair outbox need ``require_machine=walrus``;
this helper itself is durable and tippable from any host via path override.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

from _common import EXIT_ERROR, EXIT_FINDING, EXIT_OK, build_parser, resolve_homes

# Default silence before treating cmd-trace as mute (seconds).
DEFAULT_CMD_TRACE_MUTE_S = 120.0


def default_chair_outbox(env: dict | None = None) -> Path:
    """Resolve Jeeves/chair outbox: BOB_CHAIR_OUTBOX, else ~/.jeeves/outbox.txt.

    Do not use BOB_HOME / BOB_DIGEST_HOME here --- those often point at
    ``.bobiverse`` (digest), not the Jeeves identity home that drains shop-wire.
    """
    env = os.environ if env is None else env
    raw = (env.get("BOB_CHAIR_OUTBOX") or "").strip()
    if raw:
        return Path(raw)
    for key in ("JEEVES_HOME", "BOB_JEEVES_HOME"):
        home = (env.get(key) or "").strip()
        if home:
            return Path(home) / "outbox.txt"
    profile = env.get("USERPROFILE") or env.get("HOME") or str(Path.home())
    return Path(profile) / ".jeeves" / "outbox.txt"


def cmd_trace_mute_max_age_s(env: dict | None = None) -> float:
    env = os.environ if env is None else env
    raw = (env.get("BOB_CMD_TRACE_MUTE_S") or "").strip()
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    return float(DEFAULT_CMD_TRACE_MUTE_S)


def cmd_trace_path(chair_home: Path) -> Path:
    return Path(chair_home) / "cmd-trace.log"


def cmd_trace_mute_snapshot(
    chair_home: Path,
    *,
    max_age_s: float | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Return stale/age snapshot for chair cmd-trace.log (FR #9878 / #9871)."""
    path = cmd_trace_path(chair_home)
    limit = float(cmd_trace_mute_max_age_s() if max_age_s is None else max_age_s)
    out: dict[str, Any] = {
        "path": str(path),
        "max_age_s": limit,
        "stale": True,
        "age_s": None,
        "reason": "",
    }
    try:
        if not path.is_file():
            out["reason"] = "missing"
            return out
        age = float((time.time() if now is None else now) - path.stat().st_mtime)
    except OSError as e:
        out["reason"] = f"unreadable:{type(e).__name__}"
        return out
    out["age_s"] = age
    if age > limit:
        out["stale"] = True
        out["reason"] = "stale"
    else:
        out["stale"] = False
        out["reason"] = "fresh"
    return out


def machine_from_nick(nick: str) -> str:
    n = (nick or "").strip()
    if "-" in n:
        return n.rsplit("-", 1)[0].lower()
    return n.lower()


def assign_url(row: dict, *, repo: str, task: str, num: str) -> str:
    url = str(row.get("url") or row.get("html_url") or "").strip()
    if url:
        return url
    if not repo or not num:
        return ""
    kind = "pull" if task in {"MRB", "FIX"} else "issues"
    return f"https://github.com/{repo}/{kind}/{num}"


def format_assign_body(nick: str, repo: str, task: str, num: str, url: str) -> str:
    body = f"{nick}: {task} {repo}#{num} {url}".strip()
    return " ".join(body.split())


def shop_wire_lines(
    *,
    nick: str,
    repo: str,
    task: str,
    num: str,
    url: str,
    machine: str | None = None,
) -> tuple[str, str]:
    """Return (shop PRIVMSG, #bobiverse assign: sent PRIVMSG)."""
    mid = (machine or machine_from_nick(nick)).strip().lstrip("#").lower()
    body = format_assign_body(nick, repo, task, num, url)
    shop = f"PRIVMSG #{mid} :{body}"
    announce = f"PRIVMSG #bobiverse :assign: sent {body}"
    return shop, announce


def plan_to_shop_wire_lines(planned: list[dict[str, Any]]) -> list[str]:
    """Expand intervene plan dicts into shop + announce PRIVMSG lines."""
    lines: list[str] = []
    for p in planned:
        if not isinstance(p, dict):
            continue
        nick = str(p.get("nick") or "").strip()
        repo = str(p.get("repo") or "").strip()
        task = str(p.get("task") or "FR").strip().upper()
        num = str(p.get("id") or "").strip().lstrip("#")
        url = str(p.get("url") or "").strip()
        if not (nick and repo and num and url):
            continue
        shop, announce = shop_wire_lines(nick=nick, repo=repo, task=task, num=num, url=url)
        lines.append(shop)
        lines.append(announce)
    return lines


def enrich_plan_urls(planned: list[dict[str, Any]], rows_by_key: dict[str, dict]) -> list[dict[str, Any]]:
    """Attach url onto each planned assign (invent when missing)."""
    out: list[dict[str, Any]] = []
    for p in planned:
        item = dict(p)
        repo = str(item.get("repo") or "").strip()
        task = str(item.get("task") or "FR").strip().upper()
        num = str(item.get("id") or "").strip().lstrip("#")
        key = f"{repo}#{num}:{task}"
        row = rows_by_key.get(key) or {}
        item["url"] = assign_url(row if row else item, repo=repo, task=task, num=num)
        out.append(item)
    return out


def rows_index(rows: list[dict]) -> dict[str, dict]:
    import intervene_assign as ia

    idx: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        repo = ia.row_repo(row)
        num = ia.row_num(row)
        task = ia.row_task(row)
        if repo and num:
            idx[f"{repo}#{num}:{task}"] = row
    return idx


def intervene_shop_wire_from_report(
    report: dict,
    *,
    outbox: Path,
    dry_run: bool = False,
    force_needs_human: bool = False,
    pace_s: float = 0.0,
    max_assigns: int = 8,
    truncate: bool = False,
    sleeper: Callable[[float], None] | None = None,
    offerable_fn: Callable[[dict, str], bool] | None = None,
) -> dict[str, Any]:
    """Plan idle+offerable assigns and write shop-wire to Jeeves outbox (FR #9878)."""
    import intervene_assign as ia

    idle = ia.idle_from_report(report)
    rows = ia.rows_from_report(report)
    planned = ia.plan_assigns(
        idle,
        rows,
        force_needs_human=force_needs_human,
        max_assigns=max_assigns,
        offerable_fn=offerable_fn,
    )
    planned = enrich_plan_urls(planned, rows_index(rows))
    lines = plan_to_shop_wire_lines(planned)
    written = ia.append_outbox_lines(
        outbox, lines, dry_run=dry_run, pace_s=pace_s, sleeper=sleeper
    )
    payload: dict[str, Any] = {
        "ok": True,
        "mode": "shop_wire",
        "dry_run": bool(dry_run),
        "planned": planned,
        "written": written,
        "written_count": len(written),
        "outbox": str(outbox),
        "idle_count": len(idle),
        "row_count": len(rows),
        "findings": [],
    }
    if truncate and not dry_run:
        payload["truncate"] = ia.truncate_drained_outbox(outbox)
    return payload


def check(args: argparse.Namespace):
    """CLI: shop-wire intervene from fixture or idle_seats report."""
    import intervene_assign as ia

    findings: list[str] = []
    fixture = getattr(args, "fixture", "") or ""
    if fixture:
        report = json.loads(Path(fixture).read_text(encoding="utf-8-sig"))
    else:
        import idle_seats as _is

        report, code = _is.check(args)
        if code == EXIT_ERROR:
            bad = report if isinstance(report, dict) else {"ok": False}
            bad["findings"] = list(bad.get("findings") or []) + ["idle_seats error"]
            return bad, EXIT_ERROR
        if not ia.rows_from_report(report):
            try:
                from _common import queue_bucket_rows, resolve_queue_path

                chair, digest = resolve_homes(args)
                qpath = resolve_queue_path(chair, digest)
                if qpath.is_file():
                    queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
                    report = dict(report)
                    report["unaccepted"] = queue_bucket_rows(queue, "unaccepted")
            except Exception:
                pass

    outbox = Path(getattr(args, "chair_outbox", "") or default_chair_outbox())
    dry = bool(getattr(args, "dry_run", False) or getattr(args, "intervene_dry_run", False))
    force_nh = bool(getattr(args, "force_needs_human", False))
    pace = float(getattr(args, "pace_s", 0.0) or 0.0)
    max_a = int(getattr(args, "max_assigns", 8) or 8)
    truncate = bool(getattr(args, "truncate_outbox", False))

    offerable_fn = None
    if not fixture:
        try:
            chair, digest = resolve_homes(args)
            offerable_fn = ia._offerable_fn_from_homes(chair, digest)
        except Exception:
            offerable_fn = None
    if fixture and offerable_fn is None:

        def offerable_fn(row: dict, nick: str) -> bool:  # noqa: F811
            return True

    payload = intervene_shop_wire_from_report(
        report,
        outbox=outbox,
        dry_run=dry,
        force_needs_human=force_nh,
        pace_s=pace,
        max_assigns=max_a,
        truncate=truncate,
        offerable_fn=offerable_fn,
    )
    payload["findings"] = findings
    payload["ok"] = not findings
    if findings:
        return payload, EXIT_FINDING
    return payload, EXIT_OK


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = build_parser(
        "shop_wire_assign",
        "Jeeves outbox shop-wire assign when ear !assign mute (FR #9878)",
    )
    p.add_argument("--fixture", default="", help="JSON report fixture (idle_seats + unaccepted)")
    p.add_argument(
        "--chair-outbox",
        default="",
        help="Jeeves outbox.txt (default BOB_CHAIR_OUTBOX or ~/.jeeves/outbox.txt)",
    )
    p.add_argument("--intervene-dry-run", action="store_true", help="plan lines only; do not write")
    p.add_argument("--force-needs-human", action="store_true", help="allow needs_human rows")
    p.add_argument("--pace-s", type=float, default=0.0, help="seconds between outbox lines")
    p.add_argument("--max-assigns", type=int, default=8, help="cap assigns per run")
    p.add_argument("--truncate-outbox", action="store_true", help="truncate when *.pos at EOF")
    args = p.parse_args(argv)
    if getattr(args, "help_exit0", False):
        p.print_help()
        return EXIT_OK
    if args.dry_run and not args.fixture:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "mode": "shop_wire",
                    "planned": [],
                    "written": [],
                    "findings": [],
                },
                sort_keys=True,
            )
        )
        return EXIT_OK
    try:
        payload, code = check(args)
    except Exception as e:
        print(json.dumps({"ok": False, "findings": [f"shop_wire_assign error: {e}"]}, sort_keys=True))
        return EXIT_ERROR
    print(json.dumps(payload, sort_keys=True, default=str))
    return code


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
