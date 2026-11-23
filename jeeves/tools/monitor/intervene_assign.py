#!/usr/bin/env python3
"""Deterministic idle+offerable intervene via ear-relay !assign (FR #9461).

When idle shop seats coexist with offerable unaccepted rows, append
``PRIVMSG #bobiverse :!assign <nick> <repo> <TASK> <n>`` to the local ear
outbox (UTF-8 no BOM). Never edits queue.json, never touches Ergo, never
starts bob-worker. Pace default 3s between lines.

LLM monitoring is interim; this script is the token-free durable path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

from _common import EXIT_ERROR, EXIT_FINDING, EXIT_OK, build_parser, resolve_homes

_SHOP_NICK_RX = re.compile(r"^[a-z0-9][a-z0-9_.-]*-\d+$", re.I)
_TASKS = frozenset({"FR", "MRB", "UAT", "FIX", "PR", "BUILD"})


def default_ear_outbox() -> Path:
    """Prefer bob install home outbox, then digest-home outbox (FR #9461 / #8827)."""
    for key in ("BOB_EAR_OUTBOX", "BOB_OUTBOX_EAR"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return Path(raw)
    for cand in (
        Path(r"C:\ai\bob\home\outbox.txt"),
        Path(r"D:\ai\bob\home\outbox.txt"),
        Path.home() / ".bobiverse" / "outbox.txt",
    ):
        if cand.parent.is_dir():
            return cand
    return Path.home() / ".bobiverse" / "outbox.txt"


def row_num(row: dict) -> str:
    raw = str(row.get("id") or row.get("number") or "").strip()
    if raw.startswith("#"):
        raw = raw[1:]
    return raw


def row_task(row: dict) -> str:
    t = str(row.get("task") or row.get("type") or "FR").strip().upper()
    if t == "PR":
        t = "MRB"
    return t if t in _TASKS else "FR"


def row_repo(row: dict) -> str:
    return str(row.get("repo") or "").strip()


def is_mergeable_preferred(row: dict) -> bool:
    """Prefer MERGEABLE / clean merge state when stamped on the row."""
    if row.get("mergeable") is True:
        return True
    st = str(row.get("mergeable_state") or row.get("mergeStateStatus") or "").strip().upper()
    return st in {"CLEAN", "MERGEABLE", "HAS_HOOKS"}


def is_needs_human_row(row: dict, nick: str = "") -> bool:
    if row.get("needs_human"):
        return True
    try:
        import idle_seats as _is

        gc = _is._ensure_gitclaim()
        return bool(gc.row_needs_human(row, nick or ""))
    except Exception:
        return False


def is_self_mrb(row: dict, nick: str) -> bool:
    """Skip when this nick authored the PR under review (self-MRB)."""
    task = row_task(row)
    if task not in {"MRB", "UAT"}:
        return False
    me = (nick or "").strip().lower()
    if not me:
        return False
    for key in ("pr_author", "review_author", "author", "head_author", "coder"):
        val = str(row.get(key) or "").strip().lower()
        if not val:
            continue
        if val == me or me.startswith(val + "-"):
            return True
        me_mach = me.rsplit("-", 1)[0]
        val_mach = val.rsplit("-", 1)[0] if "-" in val else val
        if me_mach and me_mach == val_mach and task == "MRB" and _SHOP_NICK_RX.match(val):
            return True
    try:
        import idle_seats as _is

        gc = _is._ensure_gitclaim()
        doc = {"v": 1, "unaccepted": [row], "accepted": [], "done": []}
        cand = gc.enrich_review_author_fields(doc, row)
        live = {me}
        if gc.review_blocked_for_author(cand, nick, live):
            return True
    except Exception:
        pass
    return False


def assign_line(nick: str, repo: str, task: str, num: str) -> str:
    return f"PRIVMSG #bobiverse :!assign {nick} {repo} {task} {num}"


def plan_assigns(
    idle_seats: list[dict],
    rows: list[dict],
    *,
    force_needs_human: bool = False,
    max_assigns: int = 8,
    offerable_fn: Callable[[dict, str], bool] | None = None,
) -> list[dict[str, Any]]:
    """Pair idle nicks with rows. One assign per nick and per row id."""
    idle = [
        s
        for s in idle_seats
        if isinstance(s, dict)
        and _SHOP_NICK_RX.match(str(s.get("nick") or "").strip())
        and str(s.get("state") or "idle").lower() in {"", "idle"}
    ]
    candidates: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        repo = row_repo(row)
        num = row_num(row)
        if not repo or not num or not num.isdigit():
            continue
        if not force_needs_human and is_needs_human_row(row):
            continue
        candidates.append(row)

    def _sort_key(r: dict) -> tuple:
        task = row_task(r)
        pref = 0 if (task == "MRB" and is_mergeable_preferred(r)) else 1
        pref2 = 0 if task == "MRB" else 1
        return (pref, pref2, row_repo(r), row_num(r))

    candidates.sort(key=_sort_key)

    used_nicks: set[str] = set()
    used_rows: set[str] = set()
    planned: list[dict[str, Any]] = []

    for row in candidates:
        if len(planned) >= max_assigns:
            break
        repo = row_repo(row)
        num = row_num(row)
        task = row_task(row)
        row_key = f"{repo}#{num}:{task}"
        if row_key in used_rows:
            continue
        for seat in idle:
            nick = str(seat.get("nick") or "").strip()
            key = nick.lower()
            if not nick or key in used_nicks:
                continue
            if is_self_mrb(row, nick):
                continue
            if offerable_fn is not None:
                try:
                    if not offerable_fn(row, nick):
                        continue
                except Exception:
                    continue
            elif not force_needs_human and is_needs_human_row(row, nick):
                continue
            line = assign_line(nick, repo, task, num)
            planned.append(
                {
                    "nick": nick,
                    "repo": repo,
                    "task": task,
                    "id": num,
                    "line": line,
                    "mergeable_preferred": is_mergeable_preferred(row),
                }
            )
            used_nicks.add(key)
            used_rows.add(row_key)
            break
    return planned


def append_outbox_lines(
    outbox: Path,
    lines: list[str],
    *,
    dry_run: bool = False,
    pace_s: float = 3.0,
    sleeper: Callable[[float], None] | None = None,
) -> list[str]:
    """Append UTF-8 no-BOM PRIVMSG lines; pace between writes when not dry-run."""
    sleep = sleeper or time.sleep
    written: list[str] = []
    if dry_run:
        return list(lines)
    outbox.parent.mkdir(parents=True, exist_ok=True)
    for i, line in enumerate(lines):
        text = line if line.endswith("\n") else line + "\n"
        with outbox.open("ab") as fh:
            fh.write(text.encode("utf-8"))
        written.append(line.rstrip("\n"))
        if pace_s > 0 and i + 1 < len(lines):
            sleep(float(pace_s))
    return written


def truncate_drained_outbox(outbox: Path, pos_path: Path | None = None) -> dict[str, Any]:
    """Optional hygiene: when *.pos says EOF, truncate outbox to empty (FR #9461)."""
    if not outbox.is_file():
        return {"truncated": False, "reason": "missing"}
    pos = pos_path or outbox.with_suffix(outbox.suffix + ".pos")
    if not pos.is_file():
        alt = outbox.parent / (outbox.name + ".pos")
        pos = alt if alt.is_file() else pos
    if not pos.is_file():
        return {"truncated": False, "reason": "no_pos"}
    try:
        raw = pos.read_text(encoding="utf-8-sig").strip()
        offset = int(raw.split()[0])
    except Exception as e:
        return {"truncated": False, "reason": f"bad_pos:{e}"}
    size = outbox.stat().st_size
    if offset < size:
        return {"truncated": False, "reason": "not_drained", "pos": offset, "size": size}
    outbox.write_bytes(b"")
    try:
        pos.write_text("0\n", encoding="utf-8")
    except Exception:
        pass
    return {"truncated": True, "pos": offset, "size": size}


def rows_from_report(report: dict) -> list[dict]:
    """Pull unaccepted rows from an idle_seats-like or /report fixture."""
    if not isinstance(report, dict):
        return []
    for key in ("unaccepted", "rows", "offerable_rows"):
        raw = report.get(key)
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
    queue = report.get("queue")
    if isinstance(queue, dict) and isinstance(queue.get("unaccepted"), list):
        return [r for r in queue["unaccepted"] if isinstance(r, dict)]
    return []


def idle_from_report(report: dict) -> list[dict]:
    raw = report.get("idle_seats") if isinstance(report, dict) else None
    if isinstance(raw, list):
        return [s for s in raw if isinstance(s, dict)]
    return []


def intervene_from_report(
    report: dict,
    *,
    outbox: Path,
    dry_run: bool = False,
    force_needs_human: bool = False,
    pace_s: float = 3.0,
    max_assigns: int = 8,
    truncate: bool = False,
    sleeper: Callable[[float], None] | None = None,
    offerable_fn: Callable[[dict, str], bool] | None = None,
) -> dict[str, Any]:
    idle = idle_from_report(report)
    rows = rows_from_report(report)
    planned = plan_assigns(
        idle,
        rows,
        force_needs_human=force_needs_human,
        max_assigns=max_assigns,
        offerable_fn=offerable_fn,
    )
    lines = [p["line"] for p in planned]
    written = append_outbox_lines(
        outbox, lines, dry_run=dry_run, pace_s=pace_s, sleeper=sleeper
    )
    payload: dict[str, Any] = {
        "ok": True,
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
        payload["truncate"] = truncate_drained_outbox(outbox)
    return payload


def _offerable_fn_from_homes(chair: Path, digest: Path):
    """Bind gitclaim eligibility using local queue when present."""
    try:
        import idle_seats as _is
        from _common import ops_home, queue_bucket_rows, resolve_queue_path

        qpath = resolve_queue_path(chair, digest)
        if not qpath.is_file():
            return None
        queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
        unaccepted = queue_bucket_rows(queue, "unaccepted")
        home = ops_home(chair, digest)
        if qpath.parent != home:
            home = qpath.parent
        gc = _is._ensure_gitclaim()
        now = time.time()
        try:
            doc = gc.load_queue(home) if hasattr(gc, "load_queue") else None
        except Exception:
            doc = None
        if not isinstance(doc, dict):
            doc = {"v": 1, "unaccepted": unaccepted, "accepted": [], "done": []}
        else:
            doc = dict(doc)
            doc["unaccepted"] = unaccepted
        try:
            ledger = gc.ledger_load(home)
        except Exception:
            ledger = {}
        live = set(gc.live_seat_nicks(home) or [])

        def _fn(row: dict, nick: str) -> bool:
            live2 = set(live)
            live2.add((gc.canonical_worker_nick(nick) or nick).strip())
            return _is._row_offerable_to_nick(gc, doc, ledger, live2, row, nick, now, home)

        return _fn
    except Exception:
        return None


def check(args: argparse.Namespace):
    """CLI check entry: plan/write assigns from idle_seats report or --fixture."""
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
        if not rows_from_report(report):
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

    outbox = Path(getattr(args, "ear_outbox", "") or default_ear_outbox())
    dry = bool(getattr(args, "dry_run", False) or getattr(args, "intervene_dry_run", False))
    force_nh = bool(getattr(args, "force_needs_human", False))
    pace = float(getattr(args, "pace_s", 3.0) or 3.0)
    if pace < 3.0 and not getattr(args, "allow_fast_pace", False):
        pace = 3.0
    max_a = int(getattr(args, "max_assigns", 8) or 8)
    truncate = bool(getattr(args, "truncate_outbox", False))

    offerable_fn = None
    if not fixture:
        try:
            chair, digest = resolve_homes(args)
            offerable_fn = _offerable_fn_from_homes(chair, digest)
        except Exception:
            offerable_fn = None

    if fixture and offerable_fn is None:

        def offerable_fn(row: dict, nick: str) -> bool:  # noqa: F811
            return True

    payload = intervene_from_report(
        report,
        outbox=outbox,
        dry_run=dry,
        force_needs_human=force_nh,
        pace_s=pace,
        max_assigns=max_a,
        truncate=truncate,
        offerable_fn=offerable_fn,
    )
    idle_n = len(idle_from_report(report))
    try:
        offerable = int(report.get("offerable_for_live_seats") or 0)
    except (TypeError, ValueError):
        offerable = len(rows_from_report(report))
    if idle_n > 0 and offerable > 0 and payload["written_count"] == 0:
        if dry and payload["planned"]:
            pass
        else:
            findings.append(
                f"idle+offerable but intervene planned/wrote 0 assigns "
                f"(idle={idle_n} offerable={offerable})"
            )
    payload["findings"] = findings
    payload["ok"] = not findings
    payload["source_offerable"] = offerable
    if findings:
        return payload, EXIT_FINDING
    return payload, EXIT_OK


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = build_parser(
        "intervene_assign",
        "Ear-relay !assign when idle seats have offerable work (FR #9461)",
    )
    p.add_argument("--fixture", default="", help="JSON report fixture (idle_seats + unaccepted)")
    p.add_argument("--ear-outbox", default="", help="ear outbox.txt path (UTF-8 no BOM append)")
    p.add_argument("--intervene-dry-run", action="store_true", help="plan lines only; do not write")
    p.add_argument("--force-needs-human", action="store_true", help="allow needs_human rows")
    p.add_argument("--pace-s", type=float, default=3.0, help="seconds between outbox lines (min 3)")
    p.add_argument("--allow-fast-pace", action="store_true", help="allow pace-s < 3 (tests)")
    p.add_argument("--max-assigns", type=int, default=8, help="cap assigns per run")
    p.add_argument("--truncate-outbox", action="store_true", help="truncate when *.pos at EOF")
    args = p.parse_args(argv)
    if getattr(args, "help_exit0", False):
        p.print_help()
        return EXIT_OK
    if args.dry_run and not args.fixture:
        print(
            json.dumps(
                {"ok": True, "dry_run": True, "planned": [], "written": [], "findings": []},
                sort_keys=True,
            )
        )
        return EXIT_OK
    try:
        payload, code = check(args)
    except Exception as e:
        print(json.dumps({"ok": False, "findings": [f"intervene_assign error: {e}"]}, sort_keys=True))
        return EXIT_ERROR
    print(json.dumps(payload, sort_keys=True, default=str))
    return code


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
