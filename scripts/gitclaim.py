#!/usr/bin/env python3
"""GIT job queue owned by the digest webhook. No model calls.

POST /bob/v1/git appends claimable work. GET /bob/v1/report lists
queue.unaccepted and queue.accepted. POST /bob/v1/report op=git-claim
pops the oldest unaccepted row and stamps it accepted in one step.

Jeeves does that POST when a shop worker sends !BORED, then announces
``{repo} {task} {id}``. !ACCEPT does not claim. FILE v1 ACCEPT is unrelated.

On-disk queue.json is the listener's crash mirror of that webhook list.
It is not a second source of truth.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import bobreport

IDLE_S = 120.0
QUEUE_NAME = "queue.json"
LEGACY_UNACCEPTED = "git-unaccepted.json"
LEGACY_ACCEPTED = "git-accepted.jsonl"
ACTIVITY_NAME = "git-worker-activity.json"
LOCK_NAME = "git-claim.lock"
ACCEPTED_CAP = 200

# Task vocabulary. The GIT allowlist below is unchanged: only PR and MRB
# are produced from GitHub events. BUILD, FIX, and UAT are valid kinds if a
# row is already on the queue; this map does not emit them.
TASK_KINDS = frozenset({"FR", "PR", "BUILD", "MRB", "FIX", "UAT"})
# Issues are FR (not PR). PR open/ready -> MRB. Legacy PR rows still valid.
CLAIM_ACTIONS: dict[tuple[str, str], str] = {
    ("issues", "opened"): "FR",
    ("issues", "reopened"): "FR",
    ("pull_request", "opened"): "MRB",
    ("pull_request", "ready_for_review"): "MRB",
}
CLOSES_RE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s+#(\d+)\b"
)

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ID_RE = re.compile(r"^#\d+$")

NAK_BORED_WAIT = "NAK !BORED wait"
NAK_BORED_BUSY = "NAK !BORED busy"
NO_JOBS = "no jobs"
# FR #208 (updated Simon 2026-09-25): one line per job, no flood.
LIST_RATE_S = 30.0
LIST_MAX_LINES = 10  # job lines; + optional 1 summary + 1 more-hint <= ~12 total
LIST_LINE_MAX = 400  # bytes budget; only title is truncated
_LIST_LAST: dict[str, float] = {}


@dataclass(frozen=True)
class GitClaim:
    repo: str
    task: str
    id: str
    event: str
    action: str
    line: str
    refs: tuple[str, ...] = ()  # linked issue ids e.g. ("#19",) when PR supersedes FR
    merged: bool | None = None  # pull_request closed: True if merged


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root(home: Path) -> Path:
    return bobreport.fleet_digest_home(Path(home))


def queue_path(home: Path) -> Path:
    return _root(home) / QUEUE_NAME


def activity_path(home: Path) -> Path:
    return _root(home) / ACTIVITY_NAME


def format_claimed(job: dict) -> str:
    """Shop line for the single claimed row. Webhook field order, no !TASK."""
    return f"{job.get('repo') or ''} {job.get('task') or ''} {job.get('id') or ''}".strip()


def is_bored_command(body: str) -> bool:
    return (body or "").strip().lower() == "!bored"


def is_accept_command(body: str) -> bool:
    parts = (body or "").strip().split(None, 1)
    return bool(parts) and parts[0].lower() == "!accept"


def is_list_command(body: str) -> bool:
    """True for !list and optional filters: !list fr|mrb|uat|repo."""
    parts = (body or "").strip().split()
    return bool(parts) and parts[0].lower() == "!list"


def is_help_command(body: str) -> bool:
    """True for !help and !help <cmd> (FR #224 / gh-Jeeves #27)."""
    parts = (body or "").strip().split()
    return bool(parts) and parts[0].lower() == "!help"


_HELP_LAST: dict[str, float] = {}
HELP_RATE_S = 30.0

# Chair-visible commands (registry-lite; keep in sync with docs)
_HELP_INDEX = (
    ("!help [cmd]", "list commands or detail one (PM only)", "all"),
    ("!list [all|<repo>]", "unaccepted queue, one PM line per job", "all"),
    ("!status", "version/uptime/queue counts (when enabled)", "all"),
    ("!resync", "rebuild queue from GitHub now", "simon,bob-*"),
)


def reset_help_rate() -> None:
    _HELP_LAST.clear()


def help_rate_ok(nick: str, now: float) -> bool:
    key = (nick or "").strip().lower()
    if not key:
        return False
    last = _HELP_LAST.get(key)
    if last is not None and (float(now) - last) < HELP_RATE_S:
        return False
    _HELP_LAST[key] = float(now)
    return True


def help_rate_notice(nick: str, now: float) -> str:
    key = (nick or "").strip().lower()
    last = _HELP_LAST.get(key)
    if last is None:
        return "(help rate)"
    left = HELP_RATE_S - (float(now) - last)
    return f"(help sent; wait {int(max(0.0, left))}s)"


def format_help_lines(body: str, *, asker: str = "") -> list[str]:
    """PM lines for !help / !help <cmd>. One line per command; detail <=5 lines."""
    parts = (body or "").strip().split()
    arg = parts[1].lower().lstrip("!") if len(parts) > 1 else None
    asker_l = (asker or "").strip().lower()
    is_priv = asker_l == "simon" or asker_l.startswith("bob-")

    if arg:
        for syntax, summary, who in _HELP_INDEX:
            name = syntax.split()[0].lstrip("!").lower()
            if name != arg and not syntax.lower().startswith(f"!{arg}"):
                continue
            if who != "all" and not is_priv:
                return ["unknown command; try !help"]
            lines = [
                f"syntax: {syntax}",
                f"what: {summary}",
                f"who: {who}",
                f"example: {syntax.split()[0]}",
                "note: ACK/DONE/!bored are shop wire in #{machine}; Jeeves assigns (gh-Jeeves#106)",
            ]
            return lines[:5]
        return ["unknown command; try !help"]

    out: list[str] = []
    for syntax, summary, who in _HELP_INDEX:
        if who != "all" and not is_priv:
            continue
        out.append(f"{syntax} - {summary} [{who}]")
    out.append(
        "note: ACK/DONE/NACK/!bored in #{machine}; bob-* ear does not OFFER (Jeeves assigns)"
    )
    return out


def parse_list_command(body: str) -> tuple[str | None, str | None, bool]:
    """Return (task_filter, repo_filter, list_all)."""
    parts = (body or "").strip().split()
    if not parts or parts[0].lower() != "!list":
        return None, None, False
    task_f: str | None = None
    repo_f: str | None = None
    list_all = False
    for p in parts[1:]:
        up = p.upper()
        low = p.lower()
        if low in ("all", "full"):
            list_all = True
            continue
        if up in TASK_KINDS or up in ("FR", "MRB", "UAT", "PR", "FIX", "BUILD"):
            task_f = up
        elif REPO_RE.fullmatch(p) or ("/" in p and len(p) < 120):
            repo_f = p
    return task_f, repo_f, list_all


def reset_list_rate() -> None:
    _LIST_LAST.clear()


def list_rate_ok(nick: str, now: float) -> bool:
    """True if nick may receive a full list; stamps last time when True."""
    key = (nick or "").strip().lower()
    if not key:
        return False
    last = _LIST_LAST.get(key)
    if last is not None and (float(now) - last) < LIST_RATE_S:
        return False
    _LIST_LAST[key] = float(now)
    return True


def list_rate_remaining_s(nick: str, now: float) -> float:
    key = (nick or "").strip().lower()
    last = _LIST_LAST.get(key)
    if last is None:
        return 0.0
    left = LIST_RATE_S - (float(now) - last)
    return max(0.0, left)


def list_rate_notice(nick: str, now: float) -> str:
    left = list_rate_remaining_s(nick, now)
    ago = LIST_RATE_S - left
    if ago < 0:
        ago = 0.0
    return f"(list sent {int(ago)}s ago)"


def _job_title(row: dict) -> str:
    if str(row.get("title") or "").strip():
        return str(row.get("title")).strip()
    line = str(row.get("line") or "")
    # GIT issues repo opened #N title by user — title is mid tokens
    if " by " in line:
        mid = line.rsplit(" by ", 1)[0]
        parts = mid.split()
        # drop GIT event repo action #id
        if len(parts) >= 5 and parts[0] == "GIT":
            return " ".join(parts[5:]).strip()
    return ""


def _job_age(row: dict, *, now: float | None = None) -> str:
    """Compact age from ts/accepted_ts (e.g. 5m, 2h, 1d)."""
    import time as _time

    raw = str(row.get("ts") or row.get("accepted_ts") or "").strip()
    if not raw:
        return "?"
    try:
        # 2026-09-25T12:00:00Z
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        from datetime import datetime

        dt = datetime.fromisoformat(raw)
        ts = dt.timestamp()
    except ValueError:
        return "?"
    now_f = _time.time() if now is None else float(now)
    sec = max(0, int(now_f - ts))
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m"
    if sec < 86400:
        return f"{sec // 3600}h"
    return f"{sec // 86400}d"


def format_list_line(
    index: int,
    row: dict,
    *,
    line_max: int = LIST_LINE_MAX,
    now: float | None = None,
) -> str:
    """One PM line: ``#1 FR owner/repo#n 2h title…`` (title truncated only)."""
    task = str(row.get("task") or "?")
    repo = str(row.get("repo") or "?")
    ident = str(row.get("id") or "?")
    age = _job_age(row, now=now)
    title = _job_title(row)
    # Fixed prefix must never be truncated away.
    head = f"#{index} {task} {repo}{ident} {age}"
    budget = max(8, int(line_max) - len(head.encode("utf-8")) - 1)
    if title:
        t_bytes = title.encode("utf-8")
        if len(t_bytes) > budget:
            # truncate on UTF-8 boundaries
            cut = title
            while cut and len(cut.encode("utf-8")) > budget - 1:
                cut = cut[:-1]
            title = cut + "…"
        line = f"{head} {title}"
    else:
        line = head
    # hard cap (should already fit)
    while len(line.encode("utf-8")) > line_max and len(line) > 1:
        line = line[:-2] + "…"
    return line


def format_unaccepted_list(
    home: Path,
    *,
    task_filter: str | None = None,
    repo_filter: str | None = None,
    list_all: bool = False,
    max_lines: int = LIST_MAX_LINES,
    line_max: int = LIST_LINE_MAX,
    now: float | None = None,
) -> list[str]:
    """PM lines for !list: optional one summary + one line per job + optional more.

    Updated FR #208: no header spam; default max 10 jobs; ``N unaccepted (showing M)``.
    """
    rows = list(load_unaccepted(home))
    rows.sort(key=_sort_key)
    if task_filter:
        tf = task_filter.upper()
        rows = [r for r in rows if str(r.get("task") or "").upper() == tf]
    if repo_filter:
        rf = repo_filter.lower()
        rows = [r for r in rows if str(r.get("repo") or "").lower() == rf]
    if not rows:
        return ["queue empty"]
    total = len(rows)
    cap = max(1, int(max_lines))
    if list_all:
        cap = max(cap, total)
    show = rows[:cap]
    out: list[str] = []
    if total > len(show):
        out.append(f"{total} unaccepted (showing {len(show)})")
    elif total > 1:
        out.append(f"{total} unaccepted (showing {len(show)})")
    # single job: no summary spam — just the job line
    for i, row in enumerate(show, start=1):
        out.append(format_list_line(i, row, line_max=line_max, now=now))
    more = total - len(show)
    if more > 0:
        out.append(f"+{more} more; !list all")
    return out


def parse_accept(body: str) -> tuple[str, str, str] | None:
    """Legacy line shape. Claiming ignores it. Not FILE v1 ACCEPT."""
    parts = (body or "").strip().split()
    if len(parts) != 4 or parts[0].lower() != "!accept":
        return None
    repo, task, ident = parts[1], parts[2], parts[3]
    if task not in TASK_KINDS or not REPO_RE.fullmatch(repo) or not ID_RE.fullmatch(ident):
        return None
    return repo, task, ident


def parse_git_announce(line: str) -> GitClaim | None:
    """Parse a Jeeves `GIT …` line. None for ping, push, and other noise."""
    text = (line or "").strip()
    if not text.startswith(bobreport.GIT_ANNOUNCE_PREFIX):
        return None
    parts = text.split()
    if len(parts) < 5:
        return None
    event = parts[1].lower()
    repo = parts[2]
    action = parts[3].lower()
    ident = parts[4]
    task = CLAIM_ACTIONS.get((event, action))
    if task is None or not REPO_RE.fullmatch(repo) or not ID_RE.fullmatch(ident):
        return None
    return GitClaim(repo=repo, task=task, id=ident, event=event, action=action, line=text)


def _payload_repo(payload: dict) -> str:
    repo = payload.get("repository")
    if isinstance(repo, dict):
        return str(repo.get("full_name") or "").strip()
    return ""


def _payload_number(event: str, payload: dict) -> str | None:
    key = "pull_request" if event == "pull_request" else "issue" if event == "issues" else ""
    ent = payload.get(key) if key else None
    if not isinstance(ent, dict):
        return None
    num = ent.get("number")
    if isinstance(num, bool) or num is None:
        return None
    try:
        n = int(num)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    return f"#{n}"



def extract_closes_issue_ids(*texts: str) -> tuple[str, ...]:
    """Issue ids referenced via Closes/Fixes/Resolves/Refs #n (deterministic)."""
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for m in CLOSES_RE.finditer(text or ""):
            ident = f"#{int(m.group(1))}"
            if ident not in seen:
                seen.add(ident)
                found.append(ident)
    return tuple(found)


def _pr_blob(payload: dict) -> dict:
    pr = payload.get("pull_request")
    return pr if isinstance(pr, dict) else {}


def _issue_blob(payload: dict) -> dict:
    issue = payload.get("issue")
    return issue if isinstance(issue, dict) else {}


def claim_from_payload(event: str, payload: dict, *, line: str = "") -> GitClaim | None:
    """Build a claim from the GitHub webhook body. None if not a queue-driving event.

    issues opened/reopened -> FR
    pull_request opened/ready_for_review -> MRB (with refs to linked issues)
    pull_request closed -> MRB row used for supersede (merged flag set)
    issues closed -> FR/UAT removal via apply_queue_event (task FR id)
    """
    if not isinstance(payload, dict):
        return None
    ev = (event or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()
    repo = _payload_repo(payload)
    if not repo or not REPO_RE.fullmatch(repo):
        return None
    src = (line or "").strip()

    if ev == "issues" and action in ("opened", "reopened"):
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        return GitClaim(repo=repo, task="FR", id=ident, event=ev, action=action, line=src)

    if ev == "issues" and action == "closed":
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        return GitClaim(repo=repo, task="FR", id=ident, event=ev, action=action, line=src)

    if ev == "pull_request" and action in ("opened", "ready_for_review", "edited"):
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        pr = _pr_blob(payload)
        title = str(pr.get("title") or "")
        body = str(pr.get("body") or "")
        refs = extract_closes_issue_ids(title, body, src)
        task = "MRB" if action in ("opened", "ready_for_review") else "MRB"
        return GitClaim(
            repo=repo, task=task, id=ident, event=ev, action=action, line=src, refs=refs
        )

    if ev == "pull_request" and action == "closed":
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        pr = _pr_blob(payload)
        title = str(pr.get("title") or "")
        body = str(pr.get("body") or "")
        refs = extract_closes_issue_ids(title, body, src)
        merged = bool(pr.get("merged"))
        return GitClaim(
            repo=repo,
            task="MRB",
            id=ident,
            event=ev,
            action=action,
            line=src,
            refs=refs,
            merged=merged,
        )

    # legacy allowlist map for anything else
    task = CLAIM_ACTIONS.get((ev, action))
    if task is None:
        return None
    ident = _payload_number(ev, payload)
    if ident is None:
        return None
    return GitClaim(repo=repo, task=task, id=ident, event=ev, action=action, line=src)


def _remove_unaccepted(doc: dict, repo: str, task: str, ident: str) -> int:
    before = len(doc["unaccepted"])
    doc["unaccepted"] = [
        r for r in doc["unaccepted"] if not _same(r, repo, task, ident)
    ]
    return before - len(doc["unaccepted"])


def _remove_unaccepted_tasks(doc: dict, repo: str, ident: str, tasks: set[str]) -> int:
    before = len(doc["unaccepted"])
    doc["unaccepted"] = [
        r
        for r in doc["unaccepted"]
        if not (r.get("repo") == repo and r.get("id") == ident and r.get("task") in tasks)
    ]
    return before - len(doc["unaccepted"])


def _append_unaccepted(doc: dict, claim: GitClaim, **extra: str) -> str:
    if _already(doc, claim.repo, claim.task, claim.id):
        # refresh refs/line on existing unaccepted row
        for row in doc["unaccepted"]:
            if _same(row, claim.repo, claim.task, claim.id):
                row["line"] = claim.line
                row["event"] = claim.event
                row["action"] = claim.action
                if claim.refs:
                    row["refs"] = list(claim.refs)
                for k, v in extra.items():
                    if v:
                        row[k] = v
                return "duplicate"
        return "duplicate"
    seq = 1
    for row in doc["unaccepted"]:
        try:
            seq = max(seq, int(row.get("seq") or 0) + 1)
        except (TypeError, ValueError):
            continue
    row = {
        "repo": claim.repo,
        "task": claim.task,
        "id": claim.id,
        "ts": _utc_now(),
        "line": claim.line,
        "event": claim.event,
        "action": claim.action,
        "seq": seq,
    }
    if claim.refs:
        row["refs"] = list(claim.refs)
    for k, v in extra.items():
        if not v:
            continue
        if k == "refs" and isinstance(v, str):
            row["refs"] = [x for x in v.split(",") if x]
        else:
            row[k] = v
    doc["unaccepted"].append(row)
    return "added"


def apply_queue_event(home: Path, claim: GitClaim) -> str:
    """Apply one deterministic queue transition. Returns added|removed|updated|duplicate|error|noop."""
    if claim.task not in TASK_KINDS and claim.action not in ("closed", "edited"):
        return "error"
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error"

            ev, action = claim.event, claim.action
            changed = "noop"

            if ev == "issues" and action in ("opened", "reopened"):
                # FR for issue; drop any stale UAT for same id
                _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"UAT", "PR"})
                changed = _append_unaccepted(doc, claim)

            elif ev == "issues" and action == "closed":
                n = _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"FR", "PR", "UAT"})
                changed = "removed" if n else "noop"

            elif ev == "pull_request" and action in ("opened", "ready_for_review", "edited"):
                # Supersede linked FRs with this MRB
                for ref in claim.refs:
                    _remove_unaccepted_tasks(doc, claim.repo, ref, {"FR", "PR", "UAT"})
                extra = {}
                if claim.refs:
                    extra["refs"] = ",".join(claim.refs)
                changed = _append_unaccepted(doc, claim, **extra)

            elif ev == "pull_request" and action == "closed":
                _remove_unaccepted(doc, claim.repo, "MRB", claim.id)
                if claim.merged:
                    # PASS path: UAT for each linked open issue (queue UAT rows)
                    for ref in claim.refs:
                        _remove_unaccepted_tasks(doc, claim.repo, ref, {"FR", "PR", "MRB"})
                        uat = GitClaim(
                            repo=claim.repo,
                            task="UAT",
                            id=ref,
                            event="issues",
                            action="uat",
                            line=claim.line,
                            refs=(claim.id,),
                        )
                        _append_unaccepted(doc, uat)
                    changed = "updated"
                else:
                    # closed without merge: restore FR for linked issues
                    for ref in claim.refs:
                        fr = GitClaim(
                            repo=claim.repo,
                            task="FR",
                            id=ref,
                            event="issues",
                            action="reopened",
                            line=claim.line,
                        )
                        _append_unaccepted(doc, fr)
                    changed = "updated"
            else:
                # plain enqueue
                changed = _append_unaccepted(doc, claim)

            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error"
            return changed
    except (TimeoutError, OSError):
        return "error"



def canonical_worker_nick(nick: str) -> str | None:
    parsed = bobreport.parse_worker_nick(nick)
    if not parsed:
        return None
    try:
        return bobreport.worker_nick(parsed[0], parsed[1])
    except ValueError:
        return None


def _channel(target: str) -> str:
    return bobreport.normalize_channel(target).lower()


def worker_shop_channel(nick: str) -> str | None:
    parsed = bobreport.parse_worker_nick(nick)
    if not parsed:
        return None
    try:
        return bobreport.shop_channel(parsed[0]).lower()
    except ValueError:
        return None


def worker_working_on(home: Path, nick: str) -> str:
    """Digest working_on for this worker pid. Empty if the worker is absent."""
    parsed = bobreport.parse_worker_nick(nick)
    if not parsed:
        return ""
    mid, pid = parsed
    doc = bobreport.load_digest(_root(home))
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    ent = machines.get(mid) if isinstance(machines.get(mid), dict) else {}
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    row = workers.get(str(pid))
    if not isinstance(row, dict):
        return ""
    return str(row.get("working_on") or "").strip()


@contextmanager
def _lock(home: Path):
    root = _root(home)
    root.mkdir(parents=True, exist_ok=True)
    path = root / LOCK_NAME
    deadline = time.time() + 5.0
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 30:
                    path.unlink()
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError("git-claim lock")
            time.sleep(0.02)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            path.unlink()
        except OSError:
            pass


def _empty_queue() -> dict:
    return {"v": 1, "unaccepted": [], "accepted": []}


def _coerce_row(row: dict) -> dict | None:
    repo = str(row.get("repo") or "").strip()
    task = str(row.get("task") or "").strip()
    ident = str(row.get("id") or "").strip()
    if not repo or task not in TASK_KINDS or not ID_RE.fullmatch(ident):
        return None
    out = {
        "repo": repo,
        "task": task,
        "id": ident,
        "ts": str(row.get("ts") or ""),
        "line": str(row.get("line") or ""),
        "event": str(row.get("event") or ""),
        "action": str(row.get("action") or ""),
    }
    try:
        out["seq"] = int(row.get("seq") or 0)
    except (TypeError, ValueError):
        out["seq"] = 0
    for key in ("nick", "channel", "accepted_ts", "offered_to", "offered_ts", "offered_channel"):
        if row.get(key):
            out[key] = str(row.get(key))
    if row.get("refs"):
        refs = row.get("refs")
        if isinstance(refs, list):
            out["refs"] = [str(x) for x in refs]
        else:
            out["refs"] = str(refs)
    return out


def _read_legacy_unaccepted(path: Path) -> list[dict]:
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    items = doc.get("items") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for row in items:
        if isinstance(row, dict):
            coerced = _coerce_row(row)
            if coerced:
                out.append(coerced)
    return out


def _read_legacy_accepted(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        text = raw.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            coerced = _coerce_row(row)
            if coerced:
                rows.append(coerced)
    return rows


def _read_queue_file(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("queue")
    unaccepted = doc.get("unaccepted")
    accepted = doc.get("accepted")
    if not isinstance(unaccepted, list) or not isinstance(accepted, list):
        raise ValueError("queue lists")
    return {
        "v": 1,
        "unaccepted": [row for row in (_coerce_row(r) for r in unaccepted if isinstance(r, dict)) if row],
        "accepted": [row for row in (_coerce_row(r) for r in accepted if isinstance(r, dict)) if row],
    }


def _write_queue(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _load_queue_unlocked(home: Path) -> dict:
    path = queue_path(home)
    if path.exists():
        return _read_queue_file(path)
    root = _root(home)
    legacy_u = _read_legacy_unaccepted(root / LEGACY_UNACCEPTED)
    legacy_a = _read_legacy_accepted(root / LEGACY_ACCEPTED)
    if legacy_u or legacy_a:
        doc = {"v": 1, "unaccepted": legacy_u, "accepted": legacy_a[-ACCEPTED_CAP:]}
        _write_queue(path, doc)
        return doc
    return _empty_queue()


def load_queue(home: Path) -> dict:
    """Webhook mirror. Empty lists when nothing has been queued."""
    try:
        with _lock(home):
            return _load_queue_unlocked(home)
    except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
        return _empty_queue()


def _same(row: dict, repo: str, task: str, ident: str) -> bool:
    return row.get("repo") == repo and row.get("task") == task and row.get("id") == ident


def _already(doc: dict, repo: str, task: str, ident: str) -> bool:
    return any(_same(row, repo, task, ident) for row in doc["unaccepted"]) or any(
        _same(row, repo, task, ident) for row in doc["accepted"]
    )


def enqueue_unaccepted(home: Path, claim: GitClaim) -> str:
    """Apply deterministic queue transition for this claim (FR #207 supersede table)."""
    if claim.task not in TASK_KINDS:
        return "error"
    result = apply_queue_event(home, claim)
    if result in ("added", "updated", "removed", "duplicate", "noop"):
        # map to legacy return values for callers
        if result == "added":
            return "added"
        if result == "duplicate":
            return "duplicate"
        if result == "error":
            return "error"
        return "added" if result in ("updated", "removed") else "duplicate"
    return "error"


def load_unaccepted(home: Path) -> list[dict]:
    return list(load_queue(home).get("unaccepted") or [])


def load_accepted(home: Path) -> list[dict]:
    return list(load_queue(home).get("accepted") or [])


def _sort_key(row: dict) -> tuple:
    try:
        seq = int(row.get("seq") or 0)
    except (TypeError, ValueError):
        seq = 0
    return (
        seq,
        str(row.get("ts") or ""),
        str(row.get("repo") or ""),
        str(row.get("task") or ""),
        str(row.get("id") or ""),
    )


def claim_top(home: Path, nick: str, channel: str) -> tuple[str, dict | None]:
    """Atomically move the oldest unaccepted row to accepted.

    Returns (\"ok\", job), (\"empty\", None), or (\"error\", None).
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            if not doc["unaccepted"]:
                return "empty", None
            doc["unaccepted"].sort(key=_sort_key)
            job = dict(doc["unaccepted"].pop(0))
            job["nick"] = (nick or "").strip()
            job["channel"] = bobreport.normalize_channel(channel) if channel else ""
            job["accepted_ts"] = _utc_now()
            doc["accepted"].append(job)
            if len(doc["accepted"]) > ACCEPTED_CAP:
                doc["accepted"] = doc["accepted"][-ACCEPTED_CAP:]
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def claim_top_http(nick: str, channel: str) -> tuple[str, dict | None]:
    """POST op=git-claim to the digest webhook. Jeeves must not read queue.json."""
    import bobcallback
    import post_working_on

    secret = bobcallback.load_secret()
    url = post_working_on.report_url()
    if not secret or not url:
        return "error", None
    body = json.dumps(
        {"op": "git-claim", "nick": (nick or "").strip(), "channel": (channel or "").strip()}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Bob-Secret": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = int(resp.status)
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return "error", None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "error", None
    if status != 200:
        return "error", None
    try:
        doc = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return "error", None
    if not isinstance(doc, dict) or not doc.get("ok"):
        return "error", None
    claimed = doc.get("claimed")
    if claimed is None:
        return "empty", None
    if not isinstance(claimed, dict):
        return "error", None
    return "ok", claimed


def _read_activity(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    seen = doc.get("seen") if isinstance(doc, dict) else None
    if not isinstance(seen, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in seen.items():
        try:
            out[str(key)] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _write_activity(path: Path, seen: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"v": 1, "seen": seen}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def note_worker_activity(home: Path, nick: str, now: float) -> None:
    canon = canonical_worker_nick(nick)
    if not canon:
        return
    try:
        with _lock(home):
            path = activity_path(home)
            try:
                seen = _read_activity(path)
            except (OSError, json.JSONDecodeError):
                seen = {}
            seen[canon] = float(now)
            _write_activity(path, seen)
    except (TimeoutError, OSError, json.JSONDecodeError):
        return


def last_worker_activity(home: Path, nick: str) -> float | None:
    canon = canonical_worker_nick(nick)
    if not canon:
        return None
    try:
        with _lock(home):
            seen = _read_activity(activity_path(home))
    except (OSError, json.JSONDecodeError, TimeoutError, ValueError):
        return None
    val = seen.get(canon)
    return float(val) if val is not None else None



def offer_top(home: Path, nick: str, channel: str) -> tuple[str, dict | None]:
    """Peek oldest unaccepted and stamp offered_to without accepting (FR #207)."""
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            if not doc["unaccepted"]:
                return "empty", None
            doc["unaccepted"].sort(key=_sort_key)
            job = dict(doc["unaccepted"][0])
            job["offered_to"] = (nick or "").strip()
            job["offered_ts"] = _utc_now()
            job["offered_channel"] = bobreport.normalize_channel(channel) if channel else ""
            doc["unaccepted"][0] = job
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def parse_worker_ack(body: str) -> bool:
    """True if shop line is an ACK (not FILE v1 ACCEPT)."""
    text = (body or "").strip()
    if not text:
        return False
    # bare ACK or "nick: ACK ..." or "ACK ASSIGN ..."
    low = text.lower()
    if low == "ack":
        return True
    if re.match(r"(?i)^@?\S+[:\s]+ack\b", text):
        return True
    if re.match(r"(?i)^ack\b", text):
        return True
    return False


def accept_offered(home: Path, nick: str, channel: str) -> tuple[str, dict | None]:
    """Move offered unaccepted row for this nick to accepted (ACK in #machine)."""
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            canon = (nick or "").strip()
            idx = None
            for i, row in enumerate(doc["unaccepted"]):
                if str(row.get("offered_to") or "").strip() == canon:
                    ch = str(row.get("offered_channel") or "").lower()
                    want = bobreport.normalize_channel(channel).lower() if channel else ""
                    if ch and want and ch != want:
                        continue
                    idx = i
                    break
            if idx is None:
                return "empty", None
            job = dict(doc["unaccepted"].pop(idx))
            job["nick"] = canon
            job["channel"] = bobreport.normalize_channel(channel) if channel else ""
            job["accepted_ts"] = _utc_now()
            doc["accepted"].append(job)
            if len(doc["accepted"]) > ACCEPTED_CAP:
                doc["accepted"] = doc["accepted"][-ACCEPTED_CAP:]
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def resync_from_github(
    home: Path,
    repos: list[str],
    *,
    fetch_json=None,
) -> dict:
    """Deterministic rebuild: open FR issues + open PRs as MRB; drop closed/superseded.

    fetch_json(url) -> dict|list for tests. Default uses gh api via urllib if available.
    """
    import urllib.request

    def _default_fetch(url: str):
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    getter = fetch_json or _default_fetch
    desired: list[GitClaim] = []
    for repo in repos:
        if not REPO_RE.fullmatch(repo):
            continue
        # open issues without open PR that closes them -> FR
        issues = getter(f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100")
        prs = getter(f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=100")
        if not isinstance(issues, list):
            issues = []
        if not isinstance(prs, list):
            prs = []
        closed_by_pr: set[str] = set()
        for pr in prs:
            if not isinstance(pr, dict):
                continue
            num = pr.get("number")
            if not isinstance(num, int):
                continue
            title = str(pr.get("title") or "")
            body = str(pr.get("body") or "")
            refs = extract_closes_issue_ids(title, body)
            for r in refs:
                closed_by_pr.add(r)
            desired.append(
                GitClaim(
                    repo=repo,
                    task="MRB",
                    id=f"#{num}",
                    event="pull_request",
                    action="opened",
                    line="",
                    refs=refs,
                )
            )
        for iss in issues:
            if not isinstance(iss, dict):
                continue
            # skip PR-shaped issues
            if iss.get("pull_request"):
                continue
            num = iss.get("number")
            if not isinstance(num, int):
                continue
            ident = f"#{num}"
            if ident in closed_by_pr:
                continue
            desired.append(
                GitClaim(
                    repo=repo,
                    task="FR",
                    id=ident,
                    event="issues",
                    action="opened",
                    line="",
                )
            )

    try:
        with _lock(home):
            doc = _empty_queue()
            for claim in desired:
                _append_unaccepted(doc, claim)
            # stable sort by repo then numeric id then task
            def sk(row: dict) -> tuple:
                ident = str(row.get("id") or "#0")
                try:
                    n = int(ident.lstrip("#"))
                except ValueError:
                    n = 0
                return (str(row.get("repo") or ""), n, str(row.get("task") or ""))

            doc["unaccepted"].sort(key=sk)
            for i, row in enumerate(doc["unaccepted"], start=1):
                row["seq"] = i
            _write_queue(queue_path(home), doc)
            return {
                "ok": True,
                "unaccepted": len(doc["unaccepted"]),
                "repos": list(repos),
            }
    except (TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def bored_gate(home: Path, nick: str, channel: str, now: float) -> str:
    """ignore, wait, busy, or ok. wait is checked before busy so retries stay quiet."""
    shop = worker_shop_channel(nick)
    if shop is None or _channel(channel) != shop:
        return "ignore"
    last = last_worker_activity(home, nick)
    if last is not None and (float(now) - last) < IDLE_S:
        return "wait"
    if worker_working_on(home, nick):
        return "busy"
    return "ok"
