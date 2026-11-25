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
    """Skip when this nick authored the PR under review (self-MRB).

    FR #9478: exact-seat only here. Same-machine sibling policy lives in
    ``review_blocked_for_author`` (soft free-other-machine). Hard machine-id
    on GitHub author fields stranded flamingo idle seats when redqueen was busy.
    """
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
    for key in (
        "author_seat",
        "implementer_seat",
        "mrb_author_seat",
        "mrb_fix_author_seat",
        "author_nick",
    ):
        val = str(row.get(key) or "").strip().lower()
        if val and val == me:
            return True
    multi = row.get("author_seats")
    if isinstance(multi, str):
        for part in multi.replace(";", ",").split(","):
            if part.strip().lower() == me:
                return True
    try:
        import idle_seats as _is

        gc = _is._ensure_gitclaim()
        doc = {"v": 1, "unaccepted": [row], "accepted": [], "done": []}
        cand = gc.enrich_review_author_fields(doc, row)
        # Sole-live={me}: soft machine-id allows siblings; exact author still blocks.
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
        # FR #9850 / #9867: tip DIRTY FIX / tip CLEAN MRB before lesson FRs.
        tip_rank = 3
        try:
            from _common import ensure_script_dir_on_path

            ensure_script_dir_on_path("tip_offer_prefer.py", "gitclaim.py")
            import tip_offer_prefer as _tip

            tip_rank = int(_tip.tip_prefer_rank(r))
        except Exception:
            tip_rank = 3
        task = row_task(r)
        pref = 0 if (task == "MRB" and is_mergeable_preferred(r)) else 1
        pref2 = 0 if task == "MRB" else (1 if task == "FIX" else 2)
        return (tip_rank, pref, pref2, row_repo(r), row_num(r))

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
        # FR #9478: for MRB, try cross-machine idle seats before same-machine siblings.
        seats_ordered = list(idle)
        if task == "MRB":
            author_mids: set[str] = set()
            for key_a in (
                "author_seat",
                "implementer_seat",
                "mrb_author_seat",
                "mrb_fix_author_seat",
                "author_nick",
                "author",
            ):
                raw_a = str(row.get(key_a) or "").strip()
                if raw_a and "-" in raw_a:
                    author_mids.add(raw_a.rsplit("-", 1)[0].lower())
            multi = row.get("author_seats")
            if isinstance(multi, str):
                for part in multi.replace(";", ",").split(","):
                    p = part.strip()
                    if p and "-" in p:
                        author_mids.add(p.rsplit("-", 1)[0].lower())
            if author_mids:
                cross = []
                same = []
                for seat in seats_ordered:
                    nick_s = str(seat.get("nick") or "").strip()
                    mid = nick_s.rsplit("-", 1)[0].lower() if "-" in nick_s else ""
                    if mid and mid in author_mids:
                        same.append(seat)
                    else:
                        cross.append(seat)
                if cross:
                    seats_ordered = cross + same
        for seat in seats_ordered:
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
    """Optional hygiene: when *.pos says EOF, truncate outbox to empty (FR #9461 / #9862)."""
    if not outbox.is_file():
        return {"truncated": False, "reason": "missing"}
    try:
        import irc_agent as _ia

        # FR #9862: migrate legacy outbox.pos → outbox.txt.pos before reading.
        _ia.ensure_canonical_outbox_pos(outbox)
        pos = Path(pos_path) if pos_path else _ia.outbox_pos_path(outbox)
    except Exception:
        pos = pos_path or Path(str(outbox) + ".pos")
        if not Path(pos).is_file():
            alt = outbox.parent / (outbox.stem + ".pos")
            pos = alt if alt.is_file() else pos
    pos = Path(pos)
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
        # Canonical cursor only; drop legacy outbox.pos (FR #9862).
        import irc_agent as _ia

        _ia.save_outbox_pos(outbox, 0)
    except Exception:
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
    chair_home: Path | None = None,
    chair_outbox: Path | None = None,
    prefer_shop_wire_on_mute: bool = False,
    force_shop_wire: bool = False,
    cmd_trace_mute_s: float | None = None,
) -> dict[str, Any]:
    """Ear-relay !assign, or FR #9878 shop-wire when cmd-trace mute / forced."""
    use_shop = bool(force_shop_wire)
    mute_snap: dict[str, Any] | None = None
    if prefer_shop_wire_on_mute and chair_home is not None and not use_shop:
        try:
            import shop_wire_assign as sw

            mute_snap = sw.cmd_trace_mute_snapshot(
                Path(chair_home), max_age_s=cmd_trace_mute_s
            )
            use_shop = bool(mute_snap.get("stale"))
        except Exception as e:
            mute_snap = {"stale": False, "reason": f"probe_error:{type(e).__name__}"}
            use_shop = False

    if use_shop:
        import shop_wire_assign as sw

        target = Path(chair_outbox) if chair_outbox else sw.default_chair_outbox()
        # Shop-wire lines are pairs; keep pace only between assigns (0 inside helper
        # when caller already paced ear path). Prefer caller pace_s as-is.
        payload = sw.intervene_shop_wire_from_report(
            report,
            outbox=target,
            dry_run=dry_run,
            force_needs_human=force_needs_human,
            pace_s=pace_s,
            max_assigns=max_assigns,
            truncate=truncate,
            sleeper=sleeper,
            offerable_fn=offerable_fn,
        )
        if mute_snap is not None:
            payload["cmd_trace_mute"] = mute_snap
        payload["force_shop_wire"] = bool(force_shop_wire)
        return payload

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
        "mode": "ear_assign",
        "dry_run": bool(dry_run),
        "planned": planned,
        "written": written,
        "written_count": len(written),
        "outbox": str(outbox),
        "idle_count": len(idle),
        "row_count": len(rows),
        "findings": [],
    }
    if mute_snap is not None:
        payload["cmd_trace_mute"] = mute_snap
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

    chair_for_mute = None
    try:
        chair_for_mute, _digest = resolve_homes(args)
    except Exception:
        chair_for_mute = None
    mute_s = float(getattr(args, "cmd_trace_mute_s", 0.0) or 0.0)
    chair_out_raw = getattr(args, "chair_outbox", "") or ""
    payload = intervene_from_report(
        report,
        outbox=outbox,
        dry_run=dry,
        force_needs_human=force_nh,
        pace_s=pace,
        max_assigns=max_a,
        truncate=truncate,
        offerable_fn=offerable_fn,
        chair_home=chair_for_mute,
        chair_outbox=Path(chair_out_raw) if chair_out_raw else None,
        prefer_shop_wire_on_mute=bool(getattr(args, "prefer_shop_wire_on_mute", False)),
        force_shop_wire=bool(getattr(args, "shop_wire", False)),
        cmd_trace_mute_s=mute_s if mute_s > 0 else None,
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
    p.add_argument(
        "--shop-wire",
        action="store_true",
        help="FR #9878: force Jeeves outbox shop-wire (skip ear !assign)",
    )
    p.add_argument(
        "--prefer-shop-wire-on-mute",
        action="store_true",
        help="FR #9878: use shop-wire when chair cmd-trace is stale/missing",
    )
    p.add_argument(
        "--chair-outbox",
        default="",
        help="Jeeves outbox.txt for shop-wire (BOB_CHAIR_OUTBOX / ~/.jeeves/outbox.txt)",
    )
    p.add_argument(
        "--cmd-trace-mute-s",
        type=float,
        default=0.0,
        help="cmd-trace silence seconds before mute (0=env/default 120)",
    )
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
