#!/usr/bin/env python3
"""GIT job queue owned by the digest webhook. No model calls.

POST /bob/v1/git appends claimable work. GET /bob/v1/report lists
queue.unaccepted and queue.accepted. (claim_top is local to Jeeves; not a network op)
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

# FR #628: the per-seat "wait" NAK after DONE/GIVEUP is off by default (0 = never NAK a seat that
# has work offerable). Set BOB_BORED_IDLE_S to restore a gate. Seat busy/cooldown rules still apply.
try:
    IDLE_S = max(0.0, float(os.environ.get("BOB_BORED_IDLE_S", "0")))
except ValueError:
    IDLE_S = 0.0
# FR #628: under repo-level focus a UAT row only counts as real work for this long after its merge.
UAT_MAX_AGE_S = 48 * 3600.0
# t856u: an FR a seat already DONE (its PR waits for MRB/merge) is not re-offered for this long.
FR_DONE_HOLD_S = 24 * 3600.0
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
# t826u: `Closes #N` and the full `Closes owner/repo#N` form (what the worker FR skill mandates in every FR PR body).
CLOSES_RE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s+(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?#(?P<num>\d+)\b"
)

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ID_RE = re.compile(r"^#\d+$")
# FR #254: DONE FR URL -> real PR repo/id (cross-repo implement PRs).
PULL_URL_RE = re.compile(
    r"https?://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(?P<num>\d+)",
    re.I,
)
# FR #595 / #247: detect issues-shaped URLs so MRB never treats them as pull targets.
ISSUE_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/(\d+)",
    re.I,
)

NAK_BORED_WAIT = "NAK !BORED wait"
NAK_BORED_BUSY = "NAK !BORED busy"
NO_JOBS = "no jobs"
# FR #208 (updated Simon 2026-09-25): one line per job, no flood.
LIST_RATE_S = 30.0
LIST_MAX_LINES = 10  # job lines; + optional 1 summary + 1 more-hint <= ~12 total
LIST_LINE_MAX = 400  # bytes budget; only title is truncated
_LIST_LAST: dict[str, float] = {}

# FR #180: after GIVEUP/NACK, do not re-offer immediately; repeated giveups need a human.
GIVEUP_COOLDOWN_S = 600.0
GIVEUP_NEEDS_HUMAN_COUNT = 2
SAFE_TO_CLOSE_RE = re.compile(r"(?i)\bsafe\s+to\s+close\b")
HARVEST_TITLE_RE = re.compile(r"(?i)^(harvest|skill)\b")
# FR #628: chair-spam records (re-offer / drain loops filed by seats) are never real FR work.
CRITICAL_SPAM_TITLE_RE = re.compile(r"(?i)^CRITICAL:|\bdrain FR-unaccepted\b|\b\d+(st|nd|rd|th)\+? re-offer\b")
# FR #133 / bobiverse#258: evergreen MRB-home boards are not FR jobs.
EVERGREEN_MRB_HOME_TITLE_RE = re.compile(
    r"(?i)\bMRB\s+home\b|\bHostile\s+MRB\s+home\b|\bMRB:\s+\S+.*\bhandoff\b",
)
SKIP_FR_LABELS = frozenset(
    {
        "skill",
        "umbrella",
        "parent-fr",
        "mrb-home",
        "mrb_home",
        "evergreen",
        "evergreen-mrb",
        # FR #595: verdict / board labels are not implementable FRs.
        "mrb",
        "mrb-pass",
        "mrb-fail",
        "mrb_pass",
        "mrb_fail",
        # FR #628: held for a human / ionos / release gate.
        "needs-human",
        "blocked",
        "release-gate",
    }
)

# Labels safe to detect in free text (title/line/body). Bare ``mrb`` is labels-only —
# otherwise titles like "harden MRB/FR routing" (#595) would false-positive.
SKIP_FR_LABELS_IN_TEXT = frozenset(
    lab for lab in SKIP_FR_LABELS if lab not in {"mrb", "skill", "needs-human", "blocked", "release-gate"}
)


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
    title: str = ""
    body: str = ""
    labels: tuple[str, ...] = ()
    state: str = ""


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
    rows = ordered_unaccepted(home, list(load_unaccepted(home)))
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



def extract_closes_issue_ids(*texts: str, repo: str = "") -> tuple[str, ...]:
    """Issue ids referenced via Closes/Fixes/Resolves/Refs #n or ``Closes owner/repo#n`` (deterministic).

    With ``repo`` given, a link that names ANOTHER repo is ignored (it closes an issue elsewhere, not a row of this repo's queue).
    """
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for m in CLOSES_RE.finditer(text or ""):
            named = (m.group("repo") or "").lower()
            if repo and named and named != repo.lower():
                continue
            ident = f"#{int(m.group('num'))}"
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


def _label_names(labels) -> tuple[str, ...]:
    out: list[str] = []
    for lab in labels or []:
        if isinstance(lab, dict):
            name = str(lab.get("name") or "").strip()
        else:
            name = str(lab or "").strip()
        if name:
            out.append(name)
    return tuple(out)


def issue_skip_fr_reason(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    state: str = "",
) -> str | None:
    """FR #180 / #258: why an issue must not become (or stay) an assignable FR row; None = ok."""
    if (state or "").strip().lower() == "closed":
        return "closed"
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    hit = labs & SKIP_FR_LABELS
    if hit:
        return f"label:{sorted(hit)[0]}"
    title_s = (title or "").strip()
    if HARVEST_TITLE_RE.match(title_s):
        return "harvest_title"
    if CRITICAL_SPAM_TITLE_RE.search(title_s):
        return "critical_spam_title"
    blob = f"{title_s}\n{body or ''}"
    if SAFE_TO_CLOSE_RE.search(blob):
        return "safe_to_close"
    # bobiverse#258 / FR #133: evergreen MRB-home boards (label or title shape).
    if EVERGREEN_MRB_HOME_TITLE_RE.search(title_s) or EVERGREEN_MRB_HOME_TITLE_RE.search(blob):
        return "evergreen_mrb_home"
    # FR #595 / MRB #603: legacy queue rows may only put board labels in line/title
    # text (empty labels). Match hyphen/underscore board tokens; not bare ``mrb``.
    blob_l = blob.lower()
    text_hits = []
    for lab in sorted(SKIP_FR_LABELS_IN_TEXT, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(lab)}(?![a-z0-9])", blob_l):
            text_hits.append(lab)
    if text_hits:
        return f"label_text:{text_hits[0]}"
    return None


def row_skip_fr_reason(row: dict) -> str | None:
    labels = row.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    # Queue rows often store the issue title in ``line`` (offer/list); fall back so
    # mrb-home / harvest title skips still fire when ``title`` was never stamped.
    title = str(row.get("title") or "").strip() or str(row.get("line") or "").strip()
    return issue_skip_fr_reason(
        title=title,
        body=str(row.get("body") or ""),
        labels=tuple(str(x) for x in labels),
        state=str(row.get("state") or ""),
    )


def _parse_iso_ts(raw: str) -> float | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def row_on_cooldown(row: dict, now: float) -> bool:
    until = _parse_iso_ts(str(row.get("cooldown_until") or ""))
    return until is not None and float(now) < until


def row_needs_human(row: dict) -> bool:
    v = row.get("needs_human")
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes")


# FR #587: machine-affinity for seats that cannot do the work (WP0 live / chair-outbox).
_REQUIRE_MACHINE_LABEL_RE = re.compile(
    r"(?i)^(?:needs|require[_-]?machine)[-_:=]([a-z0-9][a-z0-9_.-]*)$"
)
# Explicit cue → fleet machine id (normalized lowercase).
_REQUIRE_MACHINE_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    # agentic_fomprep WP0 live proof must run on DEV1
    (re.compile(r"(?i)PRIORITY_WP0_INSTANCE\s*=\s*ce-priority-dev"), "ce-priority-dev1"),
    (re.compile(r"(?i)\bce-priority-dev1\b"), "ce-priority-dev1"),
    (re.compile(r"(?i)\bce-priority-dev\b"), "ce-priority-dev1"),
    (re.compile(r"(?i)\bWP0\s+live\b"), "ce-priority-dev1"),
    (re.compile(r"(?i)\bAllowedComputer\s*[:=]\s*CE-PRIORITY-DEV1\b"), "ce-priority-dev1"),
    # chair-outbox / ionos-only FRs (same pattern as needs-ionos)
    (re.compile(r"(?i)\bneeds-ionos\b"), "ionos"),
    (re.compile(r"(?i)\bchair[- ]outbox\b"), "ionos"),
    (re.compile(r"(?i)\brequire_machine\s*=\s*ionos\b"), "ionos"),
)


def infer_require_machine(
    *,
    title: str = "",
    body: str = "",
    labels=(),
    line: str = "",
) -> str:
    """Return a fleet machine id the job must run on, or '' (FR #587).

    Labels ``needs-<machine>`` / ``require_machine:<machine>`` win first, then
    title/body/line cues (WP0 live → ce-priority-dev1, needs-ionos → ionos).
    """
    labs = labels or ()
    if isinstance(labs, str):
        labs = [labs]
    for lab in labs:
        s = str(lab or "").strip()
        m = _REQUIRE_MACHINE_LABEL_RE.match(s)
        if m:
            mid = bobreport.normalize_machine_id(m.group(1)) or m.group(1).strip().lower()
            if mid:
                return mid
        # bare needs-ionos style already covered by cue regex below via label join
    blob = "\n".join(
        [
            str(title or ""),
            str(body or ""),
            str(line or ""),
            " ".join(str(x) for x in labs),
        ]
    )
    for rx, mid in _REQUIRE_MACHINE_CUES:
        if rx.search(blob):
            return mid
    return ""


def row_require_machine(row: dict) -> str:
    """Machine id required for this queue row, if any (FR #587)."""
    stamped = str(row.get("require_machine") or "").strip().lower()
    if stamped:
        return bobreport.normalize_machine_id(stamped) or stamped
    labels = row.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    return infer_require_machine(
        title=str(row.get("title") or ""),
        body=str(row.get("body") or ""),
        labels=tuple(str(x) for x in labels),
        line=str(row.get("line") or ""),
    )


def seat_matches_require_machine(nick: str, required: str) -> bool:
    """True when nick's machine matches ``required`` (or required is empty)."""
    req = (required or "").strip().lower()
    if not req:
        return True
    req_mid = bobreport.fold_machine_id(bobreport.normalize_machine_id(req) or req)
    parsed = bobreport.parse_seat_nick(nick)
    if not parsed:
        return False
    seat_mid = bobreport.fold_machine_id(parsed[0])
    return bool(seat_mid) and seat_mid == req_mid


def row_blocked_for_machine(row: dict, nick: str) -> bool:
    """True when this seat must not be offered the row (FR #587 require_machine)."""
    req = row_require_machine(row)
    if not req:
        return False
    return not seat_matches_require_machine(nick, req)


def parse_github_pull_url(url: str) -> tuple[str, str] | None:
    """Return (owner/repo, #N) for a GitHub pull URL, else None (FR #254)."""
    m = PULL_URL_RE.search(str(url or ""))
    if not m:
        return None
    return m.group("repo"), f"#{m.group('num')}"


def fr_issue_key(repo: str, ident: str) -> str:
    """Canonical SimonBarnett/bobiverse#224 key for supersede checks."""
    r = str(repo or "").strip()
    i = str(ident or "").strip()
    if i and not i.startswith("#"):
        i = f"#{i}"
    return f"{r}{i}"


def _row_refs(row: dict) -> list[str]:
    refs = row.get("refs") or []
    if isinstance(refs, str):
        return [x for x in refs.split(",") if x]
    return [str(x) for x in refs]


def fr_superseded_by_mrb(doc: dict, repo: str, ident: str) -> bool:
    """True when an unaccepted/accepted MRB supersedes this FR (FR #254)."""
    key = fr_issue_key(repo, ident)
    ident_s = str(ident or "").strip()
    if ident_s and not ident_s.startswith("#"):
        ident_s = f"#{ident_s}"
    for bucket in ("unaccepted", "accepted"):
        for row in doc.get(bucket) or []:
            if str(row.get("task") or "").upper() != "MRB":
                continue
            if str(row.get("supersedes") or "").strip() == key:
                return True
            if str(row.get("repo") or "") == str(repo or "") and ident_s in _row_refs(row):
                return True
    return False


def fr_superseded_by_done_pr(
    doc: dict,
    repo: str,
    ident: str,
    *,
    open_pulls: dict[str, set[str]] | None = None,
    fetched_repos: set[str] | None = None,
) -> bool:
    """DONE FR with /pull/ URL keeps the issue superseded while that PR is open (FR #254).

    If the PR repo was not fetched, stay superseded (avoid re-offer when implement PR is cross-repo).
    If the PR repo was fetched and the PR is no longer open, do not block.
    """
    ident_s = str(ident or "").strip()
    if ident_s and not ident_s.startswith("#"):
        ident_s = f"#{ident_s}"
    for row in doc.get("done") or []:
        if str(row.get("task") or "").upper() != "FR":
            continue
        if str(row.get("repo") or "") != str(repo or "") or str(row.get("id") or "") != ident_s:
            continue
        parsed = parse_github_pull_url(str(row.get("url") or ""))
        if not parsed:
            continue
        pr_repo, pr_id = parsed
        if fetched_repos is not None and pr_repo not in fetched_repos:
            return True
        if open_pulls is not None:
            return pr_id in open_pulls.get(pr_repo, set())
        return True
    return False


def fr_is_superseded(
    doc: dict,
    repo: str,
    ident: str,
    *,
    open_pulls: dict[str, set[str]] | None = None,
    fetched_repos: set[str] | None = None,
) -> bool:
    """FR must not be (re)queued/offered while MRB supersedes it or implement PR is open."""
    if fr_superseded_by_mrb(doc, repo, ident):
        return True
    return fr_superseded_by_done_pr(
        doc, repo, ident, open_pulls=open_pulls, fetched_repos=fetched_repos
    )



def claim_from_payload(event: str, payload: dict, *, line: str = "") -> GitClaim | None:
    """Build a claim from the GitHub webhook body. None if not a queue-driving event.

    issues opened/reopened -> FR (skipped for skill/harvest/safe-to-close/umbrella/closed — FR #180)
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
        issue = _issue_blob(payload)
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")
        labels = _label_names(issue.get("labels"))
        state = str(issue.get("state") or "open")
        if issue_skip_fr_reason(title=title, body=body, labels=labels, state=state):
            return None
        return GitClaim(
            repo=repo,
            task="FR",
            id=ident,
            event=ev,
            action=action,
            line=src,
            title=title,
            body=body,
            labels=labels,
            state=state,
        )

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
        refs = extract_closes_issue_ids(title, body, src, repo=repo)
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
        refs = extract_closes_issue_ids(title, body, src, repo=repo)
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


def fr_implementer_seat_from_doc(doc: dict, repo: str, refs) -> str:
    """FR #593 / #227: seat nick that implemented linked FR(s), if known.

    Looks at accepted/done FR rows matching ``repo`` + ``refs`` (``#N``), then
    unaccepted FR rows (rare). Used when a PR-opened webhook creates an MRB
    without going through DONE FR (which already stamps author_seat).
    """
    ref_set = set()
    if isinstance(refs, str):
        refs = [refs]
    for r in refs or ():
        s = str(r or "").strip()
        if not s:
            continue
        if not s.startswith("#"):
            s = f"#{s.lstrip('#')}"
        ref_set.add(s)
    if not ref_set or not repo:
        return ""
    for bucket in ("accepted", "done", "unaccepted"):
        for row in doc.get(bucket) or []:
            if str(row.get("repo") or "") != repo:
                continue
            if str(row.get("task") or "").upper() != "FR":
                continue
            if str(row.get("id") or "") not in ref_set:
                continue
            nick = str(
                row.get("nick")
                or row.get("done_by")
                or row.get("implementer_seat")
                or row.get("author_seat")
                or ""
            ).strip()
            if nick and bobreport.parse_seat_nick(nick):
                return canonical_worker_nick(nick) or nick
    return ""


def _append_unaccepted(doc: dict, claim: GitClaim, **extra: str) -> str:
    if claim.task == "FR" and issue_skip_fr_reason(
        title=claim.title, body=claim.body, labels=claim.labels, state=claim.state
    ):
        return "skipped"
    if claim.task == "FR" and fr_is_superseded(doc, claim.repo, claim.id):
        return "skipped"  # FR #254: MRB / open implement PR supersedes FR
    if _already(doc, claim.repo, claim.task, claim.id):
        # refresh refs/line on existing unaccepted row
        for row in doc["unaccepted"]:
            if _same(row, claim.repo, claim.task, claim.id):
                row["line"] = claim.line
                row["event"] = claim.event
                row["action"] = claim.action
                if claim.refs:
                    row["refs"] = list(claim.refs)
                if claim.title:
                    row["title"] = claim.title
                if claim.labels:
                    row["labels"] = list(claim.labels)
                for k, v in extra.items():
                    if v:
                        row[k] = v
                _stamp_require_machine(row, claim)
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
    if claim.title:
        row["title"] = claim.title
    if claim.body:
        row["body"] = claim.body[:500]
    if claim.labels:
        row["labels"] = list(claim.labels)
    for k, v in extra.items():
        if not v:
            continue
        if k == "refs" and isinstance(v, str):
            row["refs"] = [x for x in v.split(",") if x]
        else:
            row[k] = v
    _stamp_require_machine(row, claim)
    doc["unaccepted"].append(row)
    return "added"


def _stamp_require_machine(row: dict, claim: GitClaim | None = None) -> None:
    """FR #587: persist require_machine on enqueue/refresh when cues match."""
    if str(row.get("require_machine") or "").strip():
        return
    title = str((claim.title if claim else "") or row.get("title") or "")
    body = str((claim.body if claim else "") or row.get("body") or "")
    line = str((claim.line if claim else "") or row.get("line") or "")
    labels = list(claim.labels) if claim and claim.labels else (row.get("labels") or [])
    if isinstance(labels, str):
        labels = [labels]
    req = infer_require_machine(title=title, body=body, labels=labels, line=line)
    if req:
        row["require_machine"] = req


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
                if issue_skip_fr_reason(
                    title=claim.title, body=claim.body, labels=claim.labels, state=claim.state
                ):
                    changed = "noop"
                else:
                    _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"UAT", "PR"})
                    changed = _append_unaccepted(doc, claim)
                    if changed == "skipped":
                        changed = "noop"

            elif ev == "issues" and action == "closed":
                # t826u: a closed issue drops its FR/PR rows (FR #180 point 4). A UAT row queued BY A MERGED PR is kept: every FR PR
                # carries `Closes owner/repo#N`, so the merge itself closes the issue and the UAT of that merge must still be assigned.
                n = _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"FR", "PR"})
                before = len(doc["unaccepted"])
                doc["unaccepted"] = [
                    r for r in doc["unaccepted"]
                    if not (r.get("repo") == claim.repo and r.get("id") == claim.id and r.get("task") == "UAT"
                            and r.get("action") != "uat")
                ]
                n += before - len(doc["unaccepted"])
                changed = "removed" if n else "noop"

            elif ev == "pull_request" and action in ("opened", "ready_for_review", "edited"):
                # Supersede linked FRs with this MRB
                # FR #593: stamp author_seat from FR implementer before dropping FR rows.
                implementer = fr_implementer_seat_from_doc(doc, claim.repo, claim.refs)
                for ref in claim.refs:
                    _remove_unaccepted_tasks(doc, claim.repo, ref, {"FR", "PR", "UAT"})
                extra: dict[str, str] = {}
                if claim.refs:
                    extra["refs"] = ",".join(claim.refs)
                # Real pull URL so MRB offerability never invents from a bare id (FR #595).
                extra["url"] = (
                    f"https://github.com/{claim.repo}/pull/{str(claim.id).lstrip('#')}"
                )
                if implementer:
                    extra["author_seat"] = implementer
                    extra["implementer_seat"] = implementer
                changed = _append_unaccepted(doc, claim, **extra)

            elif ev == "pull_request" and action == "closed":
                _remove_unaccepted(doc, claim.repo, "MRB", claim.id)
                if claim.merged:
                    # PASS path: UAT for each linked open issue (queue UAT rows).
                    # FR #227 / #265: carry MRB reviewer + FR implementer seats.
                    mrb_src: dict = {}
                    for bucket in ("accepted", "done"):
                        for row in doc.get(bucket) or []:
                            if (
                                str(row.get("repo") or "") == claim.repo
                                and str(row.get("task") or "").upper() == "MRB"
                                and str(row.get("id") or "") == claim.id
                            ):
                                mrb_src = dict(row)
                                break
                        if mrb_src:
                            break
                    # FR #628 / mrb-664-fix: restore per-issue UAT after merge (not repo-only UAT #0).
                    extra = uat_block_extras_from_mrb_row(mrb_src) if mrb_src else {}
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
                        _append_unaccepted(doc, uat, **extra)
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
    """Legacy ``w-<short>-<pid>`` or real seat nick ``<machine>-<pid>`` (#39 gap 1)."""
    legacy = bobreport.parse_worker_nick(nick)
    if legacy:
        try:
            return bobreport.worker_nick(legacy[0], legacy[1])
        except ValueError:
            return None
    seat = bobreport.parse_seat_nick(nick)
    if seat:
        return f"{seat[0]}-{seat[1]}"
    return None


def _channel(target: str) -> str:
    return bobreport.normalize_channel(target).lower()


def worker_shop_channel(nick: str) -> str | None:
    parsed = bobreport.parse_seat_nick(nick)
    if not parsed:
        return None
    try:
        return bobreport.shop_channel(parsed[0]).lower()
    except ValueError:
        return None


def worker_working_on(home: Path, nick: str) -> str:
    """Digest working_on for this worker pid. Empty if the worker is absent."""
    parsed = bobreport.parse_seat_nick(nick)
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
    return {"v": 1, "unaccepted": [], "accepted": [], "done": []}


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
    # author_seat/url: written by gh-Jeeves-style producers; needed by the MRB author rule and wire url (#39).
    # FR #265: implementer_seat + mrb_author_seat survive reload for UAT dual-seat block.
    # FR #180: title/labels/cooldown/needs_human must survive reload so offer/prune keep working.
    for key in ("nick", "channel", "accepted_ts", "offered_to", "offered_ts", "offered_channel",
                "author_seat", "author_nick", "author", "implementer_seat", "mrb_author_seat",
                "author_seats", "url", "title", "body", "state",
                "giveup_seats", "require_machine", "cooldown_until", "giveup_ts", "supersedes", "result", "done_ts", "done_by"):
        if row.get(key):
            out[key] = str(row.get(key))
    if row.get("refs"):
        refs = row.get("refs")
        if isinstance(refs, list):
            out["refs"] = [str(x) for x in refs]
        else:
            out["refs"] = str(refs)
    if row.get("labels"):
        labs = row.get("labels")
        if isinstance(labs, list):
            out["labels"] = [str(x) for x in labs]
        else:
            out["labels"] = [str(labs)]
    try:
        if row.get("giveup_count") is not None:
            out["giveup_count"] = int(row.get("giveup_count") or 0)
    except (TypeError, ValueError):
        pass
    if row.get("repo_uat"):
        out["repo_uat"] = True
    if row.get("merged_prs"):
        mp = row.get("merged_prs")
        out["merged_prs"] = [str(x) for x in mp] if isinstance(mp, list) else [str(mp)]
    if row_needs_human(row):
        out["needs_human"] = True
    return out


def is_repo_uat(row: dict) -> bool:
    """t853u: UAT is per REPO. Only the single repo-level UAT row (``repo_uat``) is real work."""
    return _canon_task(row) == "UAT" and bool(row.get("repo_uat"))


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
    done = doc.get("done")
    if not isinstance(unaccepted, list) or not isinstance(accepted, list):
        raise ValueError("queue lists")
    if not isinstance(done, list):
        done = []
    return {
        "v": 1,
        "unaccepted": [row for row in (_coerce_row(r) for r in unaccepted if isinstance(r, dict)) if row],
        "accepted": [row for row in (_coerce_row(r) for r in accepted if isinstance(r, dict)) if row],
        # FR #254: keep DONE rows (url/result) so FR stays superseded while implement PR is open.
        "done": [row for row in (_coerce_row(r) for r in done if isinstance(r, dict)) if row][-ACCEPTED_CAP:],
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
        doc = {"v": 1, "unaccepted": legacy_u, "accepted": legacy_a[-ACCEPTED_CAP:], "done": []}
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



OFFER_TIMEOUT_S = 90.0


def ordered_unaccepted(home: Path, rows: list[dict] | None = None) -> list[dict]:
    """Unaccepted rows in assignment order (#39 gap 2): ignored dropped, strict-focus filter,
    item rank > repo priority > seq. Same order feeds !list and !bored."""
    import focus_ignore

    if rows is None:
        rows = load_unaccepted(home)
    return focus_ignore.sort_unaccepted_rows(home, list(rows))


def _canon_task(row: dict) -> str:
    task = str(row.get("task") or "FR").upper()
    if task == "PR":
        task = "FR"
    return task if task in ("FR", "MRB", "UAT") else "FR"


def resolve_assign_url(row: dict) -> str:
    """URL for an assign line (FR #595 / #247).

    FR/UAT may invent ``/issues/{id}`` when url is missing.
    MRB may only use an existing ``/pull/N`` url, or invent from explicit
    ``pr_id`` / ``pr`` — never from the bare row/issue id alone.
    """
    task = _canon_task(row)
    repo = str(row.get("repo") or "").strip()
    url = str(row.get("url") or "").strip()
    if task == "MRB":
        if PULL_URL_RE.search(url):
            return url
        pr = str(row.get("pr_id") or row.get("pr") or "").strip().lstrip("#")
        if repo and pr:
            return f"https://github.com/{repo}/pull/{pr}"
        return ""
    if url:
        return url
    num = str(row.get("id") or "").strip().lstrip("#")
    if repo and num:
        return f"https://github.com/{repo}/issues/{num}"
    return ""


def row_url(row: dict) -> str:
    """Backward-compatible alias for ``resolve_assign_url``."""
    return resolve_assign_url(row)


def mrb_already_done(doc: dict, row: dict) -> bool:
    """FR #740: True when ``done`` already has an MRB for the same repo+#id.

    After DONE PASS/FAIL the row must not be re-offered (even if a duplicate
    lingered in ``unaccepted`` or GitHub still returns HTTP 200 for a merged PR).
    """
    if _canon_task(row) != "MRB":
        return False
    repo = str(row.get("repo") or "").strip()
    ident = str(row.get("id") or "").strip()
    if not repo or not ident:
        return False
    want = ident if ident.startswith("#") else f"#{ident.lstrip('#')}"
    for r in doc.get("done") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("task") or "").upper() != "MRB":
            continue
        if str(r.get("repo") or "").strip() != repo:
            continue
        rid = str(r.get("id") or "").strip()
        if rid == want or rid.lstrip("#") == want.lstrip("#"):
            return True
    return False


def mrb_row_offerable(
    row: dict,
    *,
    pr_exists=None,
) -> bool:
    """True when an MRB row has a resolvable pull URL (and optional live PR check).

    FR #595 / #247: never offer MRB without a real ``/pull/N`` (or explicit pr_id).
    FR #740 / #738: ``pr_exists`` must mean the pull is still **open** (merged/closed → False).
    """
    if _canon_task(row) != "MRB":
        return True
    if row.get("merged") in (True, "true", "1", 1):
        return False
    raw = str(row.get("url") or "").strip()
    if ISSUE_URL_RE.search(raw) and not PULL_URL_RE.search(raw):
        return False
    url = resolve_assign_url(row)
    if not url or not PULL_URL_RE.search(url):
        return False
    m = PULL_URL_RE.search(url)
    if not m:
        return False
    repo, num = m.group("repo"), m.group("num")
    # FR #595: pull URL must target the row's repository (no cross-repo bait-and-switch).
    row_repo = str(row.get("repo") or "").strip().lower()
    if row_repo and repo.lower() != row_repo:
        return False
    if pr_exists is None:
        return True
    try:
        return bool(pr_exists(repo, num))
    except Exception:
        # Fail closed for MRB: do not offer a possibly-fake pull URL.
        return False


def github_pr_exists_checker(
    *,
    home: Path | None = None,
    cache: dict | None = None,
):
    """Return ``pr_exists(repo, num)`` → True only for an **open** pull (FR #595 / #740).

    Merged or closed PRs still return HTTP 200 from GitHub; those must be False so
    seats are not re-offered MRB after DONE PASS/FAIL. Returns None when offline /
    no token (structural URL checks in ``mrb_row_offerable`` still apply).
    """
    try:
        import gh_filer
    except Exception:
        return None
    if home is not None:
        # Prefer digest-home token when present (chair / LocalSystem).
        os.environ.setdefault("BOB_DIGEST_HOME", str(home))
    src = gh_filer.ensure_gh_token_env()
    if src == "none":
        return None
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return None
    store: dict = cache if cache is not None else {}

    def _check(repo: str, num: str) -> bool:
        key = f"{repo}#{num}"
        if key in store:
            return store[key]
        api = f"https://api.github.com/repos/{repo}/pulls/{num}"
        req = urllib.request.Request(
            api,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "bobiverse-gitclaim",
            },
            method="GET",
        )
        ok = False
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if 200 <= int(getattr(resp, "status", 200) or 200) < 300:
                    raw = resp.read()
                    try:
                        body = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
                    except (TypeError, ValueError, UnicodeDecodeError):
                        body = {}
                    # FR #740 / #738: only open pulls are offerable MRB targets.
                    ok = str((body or {}).get("state") or "").lower() == "open"
        except urllib.error.HTTPError as e:
            ok = False
            if int(getattr(e, "code", 0) or 0) not in (404, 410):
                pass  # non-404: still fail closed for offer
        except Exception:
            ok = False
        store[key] = ok
        return ok

    return _check


def _purge_dead_mrb_unaccepted(doc: dict, *, pr_exists=None) -> int:
    """Drop unaccepted MRB rows that are already done or no longer an open pull (FR #740)."""
    before = len(doc.get("unaccepted") or [])
    kept: list[dict] = []
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        if _canon_task(row) == "MRB":
            if mrb_already_done(doc, row):
                continue
            # Always apply structural / merged-flag checks; live open-state when checker given.
            if not mrb_row_offerable(row, pr_exists=pr_exists):
                continue
        kept.append(row)
    doc["unaccepted"] = kept
    return before - len(kept)


def format_assign_line(nick: str, row: dict) -> str:
    """Wire line the seats and Watch-AgentHealth parse: ``<nick>: FR|MRB|UAT owner/repo#N url``."""
    num = str(row.get("id") or "").strip().lstrip("#")
    line = f"{nick}: {_canon_task(row)} {row.get('repo') or ''}#{num} {resolve_assign_url(row)}"
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", line)).strip()


def format_nothing_queued(nick: str) -> str:
    return f"{nick}: nothing queued"


def live_seat_nicks(home: Path) -> set[str]:
    """Seat nicks present in the digest (``<machine>-<pid>``), for the MRB author rule."""
    out: set[str] = set()
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return out
    for mid, ent in (doc.get("machines") or {}).items():
        if not isinstance(ent, dict):
            continue
        for pid in (ent.get("workers") or {}):
            if str(pid).isdigit():
                out.add(f"{mid}-{int(pid)}")
    return out


def _canon_seat_nick(raw: str) -> str:
    v = str(raw or "").strip()
    if not v or not bobreport.parse_seat_nick(v):
        return ""
    return canonical_worker_nick(v) or v


def row_author_seats(row: dict) -> list[str]:
    """All seat nicks that must not self-review / self-UAT this row (FR #227 / #265).

    Collects ``implementer_seat``, ``mrb_author_seat``, legacy ``author_seat`` /
    ``author_nick`` / ``author``, and optional ``author_seats`` (comma list).
    """
    found: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        nick = _canon_seat_nick(raw)
        if not nick:
            return
        key = nick.lower()
        if key in seen:
            return
        seen.add(key)
        found.append(nick)

    for k in ("implementer_seat", "mrb_author_seat", "author_seat", "author_nick", "author"):
        _add(str(row.get(k) or ""))
    multi = row.get("author_seats")
    if isinstance(multi, (list, tuple)):
        for item in multi:
            _add(str(item or ""))
    elif multi:
        for part in str(multi).replace(";", ",").split(","):
            _add(part)
    return found


def _row_author_seat(row: dict) -> str:
    """Primary blocked seat (legacy single-value API; prefer ``row_author_seats``)."""
    seats = row_author_seats(row)
    return seats[0] if seats else ""


def uat_block_extras_from_mrb_row(mrb_row: dict, *, mrb_nick: str = "") -> dict:
    """Build UAT stamp fields from an MRB accepted/done row (FR #265).

    ``implementer_seat`` = FR implementer (MRB ``implementer_seat`` or legacy ``author_seat``).
    ``mrb_author_seat`` = MRB reviewer nick.
    ``author_seat`` = MRB reviewer (FR #227 back-compat primary).
    """
    implementer = _canon_seat_nick(
        str(
            mrb_row.get("implementer_seat")
            or mrb_row.get("author_seat")
            or mrb_row.get("author_nick")
            or ""
        )
    )
    mrb_author = _canon_seat_nick(
        mrb_nick
        or str(mrb_row.get("nick") or mrb_row.get("done_by") or mrb_row.get("mrb_author_seat") or "")
    )
    # Prefer implementer from author_seat only when it is not the same as the MRB nick
    # (DONE FR stamps author_seat=implementer; accepted MRB nick is the reviewer).
    if implementer and mrb_author and implementer.lower() == mrb_author.lower():
        # Same seat did both: still stamp once via author_seat.
        return {"author_seat": mrb_author, "mrb_author_seat": mrb_author, "implementer_seat": mrb_author}
    out: dict[str, str] = {}
    if mrb_author:
        out["author_seat"] = mrb_author
        out["mrb_author_seat"] = mrb_author
    if implementer:
        out["implementer_seat"] = implementer
        if not out.get("author_seat"):
            out["author_seat"] = implementer
    return out


def mrb_blocked_for_author(row: dict, nick: str, live: set[str]) -> bool:
    """Do not hand an MRB/UAT to the author seat (or sibling on same machine) while another machine is live.

    FR #39 / #227 / #265: MRB and UAT must go to a different machine/seat than the
    FR implementer and/or MRB author when at least one other machine has a live seat.
    """
    return review_blocked_for_author(row, nick, live)


def review_blocked_for_author(row: dict, nick: str, live: set[str]) -> bool:
    """Shared MRB+UAT author block (FR #39 / #227 / #265).

    Blocks when ``nick`` matches any of ``row_author_seats`` (exact seat) while another
    seat is live, or is a sibling on the same machine while another machine is live.
    """
    if _canon_task(row) not in ("MRB", "UAT"):
        return False
    authors = row_author_seats(row)
    if not authors:
        return False
    me = canonical_worker_nick(nick) or nick
    live_c = {(canonical_worker_nick(n) or n).lower() for n in live}
    me_l = me.lower()
    me_p = bobreport.parse_seat_nick(me)
    me_mid = bobreport.fold_machine_id(me_p[0]) if me_p else ""

    for author in authors:
        author_l = author.lower()
        # Exact author seat: never self-MRB / self-UAT (FR #628, even if it is the only live seat).
        if author_l == me_l:
            return True
        author_p = bobreport.parse_seat_nick(author)
        # Sibling seat on the same machine: block when another machine has a live seat.
        if author_p and me_p:
            author_mid = bobreport.fold_machine_id(author_p[0])
            if author_mid == me_mid:
                for n in live_c:
                    p = bobreport.parse_seat_nick(n)
                    if p and bobreport.fold_machine_id(p[0]) != author_mid:
                        return True
    return False


def row_machine_mismatch(row: dict, nick: str) -> bool:
    """FR #628: rows pinned to a machine (``require_machine`` field or ``machine:<id>`` label)
    are never offered to a seat on another machine (they would only GIVEUP)."""
    want = str(row.get("require_machine") or "").strip().lower()
    if not want:
        for lab in row.get("labels") or ():
            m = re.match(r"(?i)^(?:machine|require-machine)[:=-](.+)$", str(lab).strip())
            if m:
                want = m.group(1).strip().lower()
                break
    if not want:
        return False
    p = bobreport.parse_seat_nick(canonical_worker_nick(nick) or nick)
    if not p:
        return True
    return bobreport.fold_machine_id(p[0]).lower() != bobreport.fold_machine_id(want).lower()


def row_gave_up_by(row: dict, nick: str) -> bool:
    seats = {x.strip().lower() for x in str(row.get("giveup_seats") or "").split(",") if x.strip()}
    me = (canonical_worker_nick(nick) or nick).strip().lower()
    return bool(seats) and (me in seats or nick.strip().lower() in seats)


def offer_focus_top(
    home: Path,
    nick: str,
    channel: str,
    *,
    now: float | None = None,
    pr_exists=None,
) -> tuple[str, dict | None]:
    """Focus-ordered offer for !bored (#39 gap 2). Stamps offered_to (ACK accepts it, FR #207).

    "ok" job | "empty" (nothing queued / nothing eligible under strict focus or ignore) | "error".
    A row offered to another seat within OFFER_TIMEOUT_S is skipped; a row already offered to
    this nick is re-offered (rebroadcast) instead of burning a second job.
    ``pr_exists`` (optional) skips MRB rows whose pull URL 404s (FR #595 / #247).
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    live = live_seat_nicks(home)
    me = (nick or "").strip()
    ledger = ledger_load(home)
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            # FR #740 / #738: drop MERGED/CLOSED/already-DONE MRB before picking.
            purged = _purge_dead_mrb_unaccepted(doc, pr_exists=pr_exists)
            order = ordered_unaccepted(home, doc["unaccepted"])
            pick = None
            for cand in order:
                if row_needs_human(cand) or row_on_cooldown(cand, now_f):
                    continue  # FR #180: GIVEUP/NACK cooldown / needs-human
                if row_skip_fr_reason(cand):
                    continue
                # FR #628: never hand out a row that is bound to GIVEUP for this seat.
                if row_machine_mismatch(cand, me) or row_gave_up_by(cand, me):
                    continue
                if ledger_blocks(ledger, cand, me, live):
                    continue  # t852u: durable self-MRB/UAT + GIVEUP memory (survives GitHub resync)
                if str(cand.get("task") or "").upper() == "FR" and fr_is_superseded(
                    doc, str(cand.get("repo") or ""), str(cand.get("id") or "")
                ):
                    continue  # FR #254
                # FR #740: never re-offer an MRB already in done (local, no token).
                if mrb_already_done(doc, cand):
                    continue
                # FR #595 / #247 / #740: skip MRB without a real open pull URL.
                if not mrb_row_offerable(cand, pr_exists=pr_exists):
                    continue
                to = str(cand.get("offered_to") or "").strip()
                if to and to.lower() != me.lower():
                    try:
                        age = now_f - datetime.fromisoformat(
                            str(cand.get("offered_ts") or "").replace("Z", "+00:00")
                        ).timestamp()
                    except ValueError:
                        age = OFFER_TIMEOUT_S + 1
                    if age < OFFER_TIMEOUT_S:
                        continue
                if review_blocked_for_author(cand, me, live):
                    continue
                # FR #587: skip seats whose machine does not match require_machine.
                if row_blocked_for_machine(cand, me):
                    continue
                pick = cand
                break
            if pick is None:
                if purged:
                    try:
                        _write_queue(queue_path(home), doc)
                    except OSError:
                        return "error", None
                return "empty", None
            for i, row in enumerate(doc["unaccepted"]):
                if row is pick or _same(row, str(pick.get("repo") or ""), str(pick.get("task") or ""), str(pick.get("id") or "")):
                    job = dict(row)
                    job["offered_to"] = me
                    job["offered_ts"] = _utc_now()
                    job["offered_channel"] = bobreport.normalize_channel(channel) if channel else ""
                    # Stamp resolved pull URL so the wire line never invents one.
                    resolved = resolve_assign_url(job)
                    if resolved:
                        job["url"] = resolved
                    doc["unaccepted"][i] = job
                    break
            else:
                return "error", None
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


def offer_top(
    home: Path,
    nick: str,
    channel: str,
    *,
    now: float | None = None,
    pr_exists=None,
) -> tuple[str, dict | None]:
    """Peek oldest eligible unaccepted and stamp offered_to without accepting (FR #207 / #180)."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            if not doc["unaccepted"]:
                return "empty", None
            purged = _purge_dead_mrb_unaccepted(doc, pr_exists=pr_exists)
            doc["unaccepted"].sort(key=_sort_key)
            pick_i = None
            for i, row in enumerate(doc["unaccepted"]):
                if row_needs_human(row) or row_on_cooldown(row, now_f) or row_skip_fr_reason(row):
                    continue
                if str(row.get("task") or "").upper() == "FR" and fr_is_superseded(
                    doc, str(row.get("repo") or ""), str(row.get("id") or "")
                ):
                    continue  # FR #254
                if mrb_already_done(doc, row):
                    continue
                if not mrb_row_offerable(row, pr_exists=pr_exists):
                    continue
                if row_blocked_for_machine(row, nick or ""):
                    continue
                pick_i = i
                break
            if pick_i is None:
                if purged:
                    try:
                        _write_queue(queue_path(home), doc)
                    except OSError:
                        return "error", None
                return "empty", None
            job = dict(doc["unaccepted"][pick_i])
            job["offered_to"] = (nick or "").strip()
            job["offered_ts"] = _utc_now()
            job["offered_channel"] = bobreport.normalize_channel(channel) if channel else ""
            resolved = resolve_assign_url(job)
            if resolved:
                job["url"] = resolved
            doc["unaccepted"][pick_i] = job
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "error", None
            return "ok", job
    except (TimeoutError, OSError):
        return "error", None


# ---------------------------------------------------------------- seat ledger (t852u)
# queue.json rows are rebuilt by GitHub resync (cooldown / giveup / author stamps are lost) and the
# done/accepted history is tiny, so author-seat stamps on rows are unreliable. This ledger is durable,
# outside queue.json, and is the authority for "this seat touched / gave up this work".
LEDGER_NAME = "seat-ledger.json"
_LEDGER_MUTEX = None


def ledger_path(home: Path) -> Path:
    return _root(home) / LEDGER_NAME


def _lkey(repo: str, ident) -> str:
    num = str(ident or "").strip().lstrip("#")
    return f"{(repo or '').strip().lower()}#{num}"


def _ledger_empty() -> dict:
    return {"v": 1, "touch": {}, "giveup": {}}


def ledger_load(home: Path) -> dict:
    try:
        doc = json.loads(ledger_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _ledger_empty()
    if not isinstance(doc, dict):
        return _ledger_empty()
    doc.setdefault("touch", {})
    doc.setdefault("giveup", {})
    doc.setdefault("uat_cycle", {})
    doc.setdefault("fr_done", {})
    return doc


def ledger_uat_cycle_done(home: Path, repo: str) -> None:
    """A repo-level UAT finished: the next UAT cycle only counts PRs merged after now (t853u)."""
    def _f(doc: dict) -> None:
        doc.setdefault("uat_cycle", {})[(repo or "").strip().lower()] = _utc_now()
    try:
        _ledger_update(home, _f)
    except OSError:
        pass


def _ledger_update(home: Path, fn) -> None:
    import threading

    global _LEDGER_MUTEX
    if _LEDGER_MUTEX is None:
        _LEDGER_MUTEX = threading.Lock()
    with _LEDGER_MUTEX:
        doc = ledger_load(home)
        fn(doc)
        p = ledger_path(home)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)


def _canon_ledger_nick(nick: str) -> str:
    return (canonical_worker_nick(nick) or (nick or "").strip()).lower()


def ledger_touch(home: Path, nick: str, repo: str, task: str, keys: list[str]) -> None:
    """Record that ``nick`` did ``task`` (FR implement / MRB review / UAT) on each ``owner/repo#N`` key."""
    me = _canon_ledger_nick(nick)
    t = (task or "").upper()
    if not me or not t or not keys:
        return

    def _f(doc: dict) -> None:
        for k in keys:
            roles = doc["touch"].setdefault(k, {}).setdefault(me, [])
            if t not in roles:
                roles.append(t)

    try:
        _ledger_update(home, _f)
    except OSError:
        pass


def ledger_giveup(home: Path, nick: str, repo: str, task: str, ident: str, refs=()) -> None:
    """``nick`` gave up (GIVEUP/NACK) this row: never offer it, or its linked PR/issue UAT/MRB, to that seat again."""
    me = _canon_ledger_nick(nick)
    if not me:
        return
    keys = [_lkey(repo, ident)] + [_lkey(repo, r) for r in (refs or ()) if str(r).strip()]

    def _f(doc: dict) -> None:
        for k in keys:
            gu = doc["giveup"].setdefault(k, {})
            tl = gu.setdefault(me, [])
            if (task or "").upper() not in tl:
                tl.append((task or "").upper())

    try:
        _ledger_update(home, _f)
    except OSError:
        pass


def _row_link_keys(row: dict) -> list[str]:
    repo = str(row.get("repo") or "")
    refs = row.get("refs") or []
    if isinstance(refs, str):
        refs = [x for x in re.split(r"[,\s]+", refs) if x]
    keys = [_lkey(repo, row.get("id"))]
    for r in refs:
        if str(r).strip():
            keys.append(_lkey(repo, r))
    sup = str(row.get("supersedes") or "").strip()
    if "#" in sup:
        keys.append(sup.lower())
    return list(dict.fromkeys(keys))


def ledger_blocks(ledger: dict, row: dict, nick: str, live=None) -> str:
    """See ``_ledger_blocks``. For the repo-level UAT (t853u) a seat that implemented any merged PR of the
    cycle is skipped, unless EVERY live seat did (then nobody could ever run it, so anyone may)."""
    why = _ledger_blocks(ledger, row, nick)
    if why and is_repo_uat(row) and "implemented" in why and live:
        seats = {s for s in live} | {nick}
        if all(_ledger_blocks(ledger, row, s) for s in seats):
            return ""
    return why


def _ledger_blocks(ledger: dict, row: dict, nick: str) -> str:
    """Why this seat must not get this row ('' = ok), from the durable ledger.

    * a seat that gave up the row (or its linked PR/issue) in the same MRB/UAT/FR family never gets it again;
    * UAT: blocked for the FR implementer and the MRB reviewer of any linked issue/PR;
    * MRB: blocked for the FR implementer of any linked issue/PR.
    """
    me = _canon_ledger_nick(nick)
    if not me:
        return ""
    task = _canon_task(row)
    keys = _row_link_keys(row)
    if task == "FR":
        done_ts = _parse_iso_ts(str((ledger.get("fr_done") or {}).get(_lkey(str(row.get("repo") or ""), row.get("id"))) or ""))
        if done_ts is not None and (time.time() - done_ts) < FR_DONE_HOLD_S:
            return "FR already delivered (PR pending merge)"
    gu = ledger.get("giveup") or {}
    own = _lkey(str(row.get("repo") or ""), row.get("id"))
    repo_level = is_repo_uat(row)
    for k in keys:
        tl = (gu.get(k) or {}).get(me) or []
        if k == own and tl:
            return f"{nick} already gave up {k}"
        if not repo_level and task in ("MRB", "UAT") and any(x in ("MRB", "UAT") for x in tl):
            return f"{nick} already gave up linked {k}"
    if task in ("MRB", "UAT"):
        bad = {"FR", "MRB"} if task == "UAT" else {"FR"}
        if repo_level:
            bad = {"FR"}          # t853u: only seats that implemented a merged PR of the cycle are excluded
        tc = ledger.get("touch") or {}
        for k in keys:
            roles = (tc.get(k) or {}).get(me) or []
            if bad & set(roles):
                return f"{nick} implemented/reviewed {k} (no self-{task})"
    return ""


def ledger_note_event(home: Path, nick: str, verb: str, task: str, repo: str, ident: str, job: dict | None = None,
                      result: str = "", url: str = "") -> None:
    """Hook for the shop wire: ACK/DONE/NACK/GIVEUP of ``task repo#ident`` by ``nick``."""
    verb_u = (verb or "").upper()
    task_u = (task or "").upper()
    job = job or {}
    keys = _row_link_keys({"repo": repo, "id": ident, "refs": job.get("refs") or [], "supersedes": job.get("supersedes") or ""})
    if verb_u in ("GIVEUP", "NACK"):
        refs = job.get("refs") or []
        if isinstance(refs, str):
            refs = [x for x in re.split(r"[,\s]+", refs) if x]
        ledger_giveup(home, nick, repo, task_u, ident, refs)
        return
    if verb_u == "DONE" and task_u == "UAT" and (job.get("repo_uat") or str(ident) == "#0"):
        ledger_uat_cycle_done(home, repo)
    if verb_u == "DONE" and task_u == "FR":
        def _fd(doc: dict) -> None:   # t856u: FR delivered (PR open elsewhere): do not re-offer the issue while it waits for the merge
            doc.setdefault("fr_done", {})[_lkey(repo, ident)] = _utc_now()
        try:
            _ledger_update(home, _fd)
        except OSError:
            pass
    if verb_u in ("ACK", "DONE") and task_u in ("FR", "MRB"):
        ledger_touch(home, nick, repo, task_u, keys)
    if verb_u == "DONE" and task_u == "FR":
        parsed = parse_github_pull_url(url or result or "")
        if parsed:
            ledger_touch(home, nick, parsed[0], "FR", [_lkey(parsed[0], parsed[1])])


def github_pr_seat_fetcher(*, home: Path | None = None):
    """Return ``fetch(repo, num) -> set[str] | None`` of seat nicks that authored commits on a PR.

    Seats commit as their nick (``marchhare-41928``), so the PR's commit authors are the ground truth for
    "who wrote this" - independent of queue history. ``set()`` = not a PR / no seat commits; ``None`` =
    could not tell (offline / no token / transient error; not cached)."""
    try:
        import gh_filer
    except Exception:
        return None
    if home is not None:
        os.environ.setdefault("BOB_DIGEST_HOME", str(home))
    if gh_filer.ensure_gh_token_env() == "none":
        return None
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return None

    def _fetch(repo: str, num: str):
        api = f"https://api.github.com/repos/{repo}/pulls/{str(num).lstrip('#')}/commits?per_page=100"
        req = urllib.request.Request(api, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-gitclaim"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            return set() if int(getattr(e, "code", 0) or 0) in (404, 410, 422) else None
        except Exception:
            return None
        out: set[str] = set()
        for c in data if isinstance(data, list) else []:
            for who in ((c.get("commit") or {}).get("author") or {}, (c.get("commit") or {}).get("committer") or {}):
                name = str(who.get("name") or "").strip().lower()
                if name and bobreport.parse_seat_nick(name):
                    out.add(name)
        return out

    return _fetch


def ledger_refresh_authors(home: Path, rows, fetch, *, limit: int = 8, ttl_s: float = 6 * 3600.0) -> int:
    """Stamp the seat ledger with the commit authors of every PR behind the MRB/UAT ``rows`` (bounded).

    The PR key and every linked key of the row get ``FR`` for each seat that committed (so that seat can
    neither review nor UAT it). Results are cached per PR key for ``ttl_s``. Returns lookups done."""
    if fetch is None:
        return 0
    import time as _time

    now_f = _time.time()
    led = ledger_load(home)
    fetched = led.get("fetched") or {}
    todo: list[tuple[str, str, list[str]]] = []
    for row in rows:
        if _canon_task(row) not in ("MRB", "UAT"):
            continue
        repo = str(row.get("repo") or "")
        keys = _row_link_keys(row)
        for k in keys:
            if k in fetched and now_f - float(fetched[k]) < ttl_s:
                continue
            if all(k != t[0] for t in todo):
                # repo-level UAT: a seat that wrote PR A must not look like the author of PR B
                todo.append((k, repo, [k, keys[0]] if is_repo_uat(row) else keys))
    done = 0
    for k, repo, keys in todo[:limit]:
        num = k.rsplit("#", 1)[1]
        try:
            seats = fetch(repo, num)
        except Exception:
            seats = None
        if seats is None:
            continue
        done += 1
        def _f(doc: dict, k=k, seats=seats, keys=keys) -> None:
            doc.setdefault("fetched", {})[k] = _time.time()
            for s in seats:
                for kk in keys:
                    roles = doc["touch"].setdefault(kk, {}).setdefault(s, [])
                    if "FR" not in roles:
                        roles.append("FR")
        try:
            _ledger_update(home, _f)
        except OSError:
            pass
    return done


_ASSIGN_CMD = re.compile(
    r"(?is)^\s*!assign\s+(\S+)\s+(\S+)\s+(FR|MRB|UAT)\s+#?(\d+)\s*$"
)


def parse_assign_cmd(body: str) -> tuple[str, str, str, str] | None:
    """``!assign <worker-nick> <repo> <FR|MRB|UAT> <num>`` -> (nick, repo, TASK, '#N') or None (t849u)."""
    m = _ASSIGN_CMD.match(body or "")
    if not m:
        return None
    return m.group(1), m.group(2).strip().strip("{}"), m.group(3).upper(), f"#{int(m.group(4))}"


def assign_row(
    home: Path,
    nick: str,
    repo: str,
    task: str,
    ident: str,
    *,
    now: float | None = None,
    pr_exists=None,
) -> tuple[str, dict | str]:
    """Chair-driven manual assign (t849u): stamp ``offered_to`` on one named unaccepted row.

    Returns ("ok", job) -> caller posts ``format_assign_line`` in the worker's shop channel as Jeeves
    and the worker's ACK accepts it (``accept_offered``); or ("refused", reason).
    The same eligibility as ``offer_focus_top`` applies: real seat nick, not busy, row queued and
    unaccepted, no self-MRB/UAT, not needs-human/skip/cooldown/machine-pinned/already given up by
    this seat, not offered to another seat inside OFFER_TIMEOUT_S.
    """
    import time as _time

    from focus_ignore import repo_match  # lazy: avoids an import cycle at module load

    now_f = _time.time() if now is None else float(now)
    me = canonical_worker_nick(nick) or (nick or "").strip()
    shop = worker_shop_channel(me)
    if shop is None:
        return "refused", f"{nick}: not a worker seat nick (<machine>-<pid>)"
    if worker_working_on(home, me):
        return "refused", f"{me}: busy ({worker_working_on(home, me)[:60]})"
    task_u = (task or "").upper()
    num = str(ident or "").strip().lstrip("#")
    live = live_seat_nicks(home)
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "refused", "queue unreadable"
            idx = None
            for i, row in enumerate(doc["unaccepted"]):
                if (
                    str(row.get("task") or "").upper() == task_u
                    and str(row.get("id") or "").strip().lstrip("#") == num
                    and repo_match(repo, str(row.get("repo") or ""))
                ):
                    idx = i
                    break
            if idx is None:
                return "refused", f"{repo}#{num} {task_u}: not in the unaccepted queue"
            cand = doc["unaccepted"][idx]
            if row_needs_human(cand):
                return "refused", "row is needs-human"
            if row_on_cooldown(cand, now_f):
                return "refused", "row is on GIVEUP/NACK cooldown"
            if row_skip_fr_reason(cand):
                return "refused", f"row skipped: {row_skip_fr_reason(cand)}"
            if row_machine_mismatch(cand, me):
                return "refused", f"row is pinned to another machine than {me}"
            if row_gave_up_by(cand, me):
                return "refused", f"{me} already gave this row up"
            why = ledger_blocks(ledger_load(home), cand, me, live)
            if why:
                return "refused", why
            if task_u == "FR" and fr_is_superseded(doc, str(cand.get("repo") or ""), str(cand.get("id") or "")):
                return "refused", "FR superseded by an open PR"
            if not mrb_row_offerable(cand, pr_exists=pr_exists):
                return "refused", "MRB has no real pull URL"
            if review_blocked_for_author(cand, me, live):
                return "refused", f"{me} authored/implemented this (no self-{task_u})"
            to = str(cand.get("offered_to") or "").strip()
            if to and to.lower() != me.lower():
                try:
                    age = now_f - datetime.fromisoformat(
                        str(cand.get("offered_ts") or "").replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    age = OFFER_TIMEOUT_S + 1
                if age < OFFER_TIMEOUT_S:
                    return "refused", f"already offered to {to}"
            job = dict(cand)
            job["offered_to"] = me
            job["offered_ts"] = _utc_now()
            job["offered_channel"] = shop
            resolved = resolve_assign_url(job)
            if resolved:
                job["url"] = resolved
            doc["unaccepted"][idx] = job
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return "refused", "queue write failed"
            return "ok", job
    except (TimeoutError, OSError):
        return "refused", "queue busy"


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


def prune_unassignable_queue(home: Path) -> dict:
    """FR #180 / #595: drop unaccepted FR verdict/junk rows and MRB rows without a real pull URL.

    Does not call GitHub. Closed-issue drops still come from webhooks + ``resync_from_github``.
    ``needs_human`` rows are kept but never offered (see ``offer_focus_top``).
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return {"ok": False, "error": "load"}
            before = len(doc["unaccepted"])
            keep = []
            for row in doc["unaccepted"]:
                task = str(row.get("task") or "").upper()
                if task == "FR" and row_skip_fr_reason(row):
                    continue
                # FR #595: drop MRB rows that cannot resolve to a real /pull/ URL.
                if task == "MRB" and not mrb_row_offerable(row):
                    continue
                # mrb-664-fix: keep per-issue UAT rows (FR #628); do not drop non-repo_uat.
                keep.append(row)
            doc["unaccepted"] = keep
            dropped = before - len(keep)
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return {"ok": False, "error": "write"}
            return {"ok": True, "dropped": dropped, "unaccepted": len(keep)}
    except (TimeoutError, OSError):
        return {"ok": False, "error": "lock"}


def resync_from_github(
    home: Path,
    repos: list[str],
    *,
    fetch_json=None,
    token: str = "",
    ignored=(),
) -> dict:
    """Rebuild FR/MRB rows from GitHub: open issues without a closing PR -> FR, open PRs -> MRB.

    Merge, not wipe (the chair runs this every 15 min):
    * rows of other kinds (UAT/BUILD/FIX/PR), ``accepted`` jobs, and rows of repos whose fetch FAILED are kept;
    * a stale FR/MRB row of a successfully fetched repo (closed/merged/superseded) is dropped;
    * skill/harvest/safe-to-close/umbrella issues are never (re)added and are pruned from unaccepted (FR #180);
    * existing rows keep their seq/offer fields; new items are appended; repos in ``ignored`` are skipped.

    ``token`` (optional) is sent as ``Authorization: Bearer``; it is never logged or returned.
    ``fetch_json(url) -> dict|list`` is the test seam; default is urllib with the token.
    """
    import urllib.request

    def _default_fetch(url: str):
        hdrs = {"Accept": "application/vnd.github+json", "User-Agent": "bobiverse-jeeves"}
        if token:
            hdrs["Authorization"] = "Bearer " + token
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    getter = fetch_json or _default_fetch
    skip = {str(x).strip().lower() for x in (ignored or ()) if str(x).strip()}
    desired: list[GitClaim] = []
    fetched: list[str] = []
    failed: list[str] = []
    open_pulls_map: dict[str, set[str]] = {}
    supersede_keys: set[str] = set()  # FR #254 owner/repo#N closed by open PR Closes
    repo_clear: dict[str, bool] = {}   # t853u: no open non-excluded issue and no open PR
    uat_plan: dict[str, tuple[list[str], list[str]]] = {}   # repo -> (merged PRs this cycle, issues they closed)
    cycles = ledger_load(home).get("uat_cycle") or {}
    for repo in repos:
        if not REPO_RE.fullmatch(repo):
            continue
        if repo.lower() in skip or repo.split("/", 1)[-1].lower() in skip:
            continue
        try:
            issues = getter(f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100")
            prs = getter(f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=100")
        except Exception:  # noqa: BLE001 - one bad repo (404/403/rate limit) must not wipe its rows
            failed.append(repo)
            continue
        fetched.append(repo)
        if not isinstance(issues, list):
            issues = []
        if not isinstance(prs, list):
            prs = []
        # t853u: repo-level UAT gate. Excluded issues (needs-human, boards/mrb-home, harvest/skill records,
        # CRITICAL spam, safe-to-close) never hold a repo back; every other open issue or any open PR does.
        blocking = [
            i for i in issues
            if isinstance(i, dict) and not i.get("pull_request") and not issue_skip_fr_reason(
                title=str(i.get("title") or ""), body=str(i.get("body") or ""),
                labels=_label_names(i.get("labels")), state=str(i.get("state") or "open"))
        ]
        repo_clear[repo] = not blocking and not [p for p in prs if isinstance(p, dict)]
        if repo_clear[repo]:
            try:
                closed_prs = getter(f"https://api.github.com/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=50")
            except Exception:  # noqa: BLE001
                closed_prs = None
            since = _parse_iso_ts(str(cycles.get(repo.lower()) or "")) or (time.time() - UAT_MAX_AGE_S)
            merged: list[str] = []
            linked: list[str] = []
            for pr in closed_prs if isinstance(closed_prs, list) else []:
                if not isinstance(pr, dict) or not pr.get("merged_at") or not isinstance(pr.get("number"), int):
                    continue
                mts = _parse_iso_ts(str(pr.get("merged_at")))
                if mts is None or mts <= since:
                    continue
                merged.append(f"#{pr['number']}")
                for r in extract_closes_issue_ids(str(pr.get("title") or ""), str(pr.get("body") or ""), repo=repo):
                    if r not in linked:
                        linked.append(r)
            if merged:
                uat_plan[repo] = (merged, linked)
        closed_by_pr: set[str] = set()
        for pr in prs:
            if not isinstance(pr, dict):
                continue
            num = pr.get("number")
            if not isinstance(num, int):
                continue
            title = str(pr.get("title") or "")
            body = str(pr.get("body") or "")
            refs = extract_closes_issue_ids(title, body, repo=repo)
            for r in refs:
                closed_by_pr.add(r)
            open_pulls_map.setdefault(repo, set()).add(f"#{num}")
            # Full Closes owner/repo#N forms supersede that FR even cross-repo (FR #254).
            for m in CLOSES_RE.finditer(f"{title}\n{body}"):
                rname = (m.group("repo") or "").strip()
                n = m.group("num")
                if rname and n:
                    supersede_keys.add(f"{rname}#{n}")
            desired.append(
                GitClaim(repo=repo, task="MRB", id=f"#{num}", event="pull_request", action="opened", line="", refs=refs)
            )
        for iss in issues:
            if not isinstance(iss, dict) or iss.get("pull_request"):
                continue
            num = iss.get("number")
            if not isinstance(num, int):
                continue
            ident = f"#{num}"
            if ident in closed_by_pr:
                continue
            if fr_issue_key(repo, ident) in supersede_keys:
                continue  # FR #254 cross-repo Closes
            title = str(iss.get("title") or "")
            body = str(iss.get("body") or "")
            labels = _label_names(iss.get("labels"))
            state = str(iss.get("state") or "open")
            if issue_skip_fr_reason(title=title, body=body, labels=labels, state=state):
                continue
            desired.append(
                GitClaim(
                    repo=repo,
                    task="FR",
                    id=ident,
                    event="issues",
                    action="opened",
                    line="",
                    title=title,
                    body=body,
                    labels=labels,
                    state=state,
                )
            )

    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            want = {(c.repo, c.task, c.id) for c in desired}
            fetched_set = set(fetched)
            before = len(doc["unaccepted"])
            keep = []
            for row in doc["unaccepted"]:
                if str(row.get("task") or "").upper() == "UAT":
                    # mrb-664-fix: keep per-issue UAT; drop only stale repo_uat when repo is no longer clear.
                    if (
                        row.get("repo_uat")
                        and row.get("repo") in fetched_set
                        and not repo_clear.get(str(row.get("repo")), True)
                        and not row.get("offered_to")
                    ):
                        continue
                if str(row.get("task") or "").upper() == "FR" and row_skip_fr_reason(row):
                    continue  # FR #180 local junk
                if str(row.get("task") or "").upper() == "FR" and fr_is_superseded(
                    doc,
                    str(row.get("repo") or ""),
                    str(row.get("id") or ""),
                    open_pulls=open_pulls_map,
                    fetched_repos=set(fetched),
                ):
                    continue  # FR #254
                if (
                    row.get("repo") in fetched_set
                    and row.get("task") in ("FR", "MRB")
                    and (row.get("repo"), row.get("task"), row.get("id")) not in want
                    and not row.get("offered_to")
                ):
                    continue  # closed / merged / superseded on GitHub
                keep.append(row)
            dropped = before - len(keep)
            doc["unaccepted"] = keep
            added = 0
            fetched_set2 = set(fetched)
            for claim in desired:
                if claim.task == "FR" and fr_is_superseded(
                    doc,
                    claim.repo,
                    claim.id,
                    open_pulls=open_pulls_map,
                    fetched_repos=fetched_set2,
                ):
                    continue  # FR #254
                mrb_url = (
                    f"https://github.com/{claim.repo}/pull/{claim.id.lstrip('#')}" if claim.task == "MRB" else ""
                )
                if any(_same(r, claim.repo, claim.task, claim.id) for r in doc["accepted"] + doc["unaccepted"]):
                    # already queued/claimed: keep its line, seq and offer fields; but an MRB row with no real pull
                    # URL is never offerable (FR #595), so heal it (t855u: resync-made MRB rows were all unofferable)
                    if mrb_url:
                        for r in doc["unaccepted"]:
                            if _same(r, claim.repo, "MRB", claim.id) and not PULL_URL_RE.search(str(r.get("url") or "")):
                                r["url"] = mrb_url
                    continue
                if _append_unaccepted(doc, claim, **({"url": mrb_url} if mrb_url else {})) == "added":
                    added += 1
            for urepo, (merged, linked) in uat_plan.items():
                if any(
                    str(r.get("repo")) == urepo and str(r.get("task") or "").upper() == "UAT" and r.get("repo_uat")
                    for r in doc["accepted"] + doc["unaccepted"]
                ):
                    continue                      # one repo UAT at a time
                uat = GitClaim(repo=urepo, task="UAT", id="#0", event="repo", action="uat",
                               line=f"UAT {urepo}: all issues closed, all PRs merged ({len(merged)} merged this cycle)",
                               refs=tuple(merged) + tuple(x for x in linked if x not in merged))
                if _append_unaccepted(doc, uat) == "added":
                    for r in doc["unaccepted"]:
                        if _same(r, urepo, "UAT", "#0"):
                            r["repo_uat"] = True
                            r["merged_prs"] = list(merged)
                            r["url"] = f"https://github.com/{urepo}"
                    added += 1

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
                "added": added,
                "dropped": dropped,
                "repos": list(fetched),
                "failed": list(failed),
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
