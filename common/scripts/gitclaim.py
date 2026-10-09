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
import contextlib
import copy
import threading
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
# FR #1323: DONE MRB (PASS/FAIL) must not be re-offered after done[] rotates or resync races.
MRB_DONE_HOLD_S = 7 * 24 * 3600.0
QUEUE_NAME = "queue.json"
LEGACY_UNACCEPTED = "git-unaccepted.json"
LEGACY_ACCEPTED = "git-accepted.jsonl"
ACTIVITY_NAME = "git-worker-activity.json"
LOCK_NAME = "git-claim.lock"
PENDING_NAME = "git-claim-pending.jsonl"
ACCEPTED_CAP = 200
# FR #1811: lock wait was 5s and dropped webhook rows under contention; default 30s (env override).
try:
    LOCK_WAIT_S = max(1.0, float(os.environ.get("BOB_GITCLAIM_LOCK_S", "30")))
except ValueError:
    LOCK_WAIT_S = 30.0
# FR #1811: keep done[] smaller so queue.json rewrite stays cheap under lock.
DONE_CAP = 100
WRITE_REPLACE_RETRIES = 8

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
# FR #785: archived / superseded repos must not be offered or enqueued.
# Keys are lower-case owner/name; values are the live successor for resync discovery.
# Keep in sync with docs/ARCHIVED_REPOS.md (all five archived 2026-10-03).
ARCHIVED_REPO_SUCCESSORS: dict[str, str] = {
    "simonbarnett/gh-jeeves": "SimonBarnett/bobiverse",
    "simonbarnett/agentic_build": "SimonBarnett/bobiverse",
    "simonbarnett/agentic_irc": "SimonBarnett/bobiverse",
    "simonbarnett/agentmonitor": "SimonBarnett/bobiverse",
    "simonbarnett/bob-design-uat": "SimonBarnett/bobiverse",
}
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
# FR #2650: intake harvest receipt PRs (GhCliFiler draft) must never become MRB.
_INTAKE_HARVEST_FOOTER_RE = re.compile(r"(?i)Invoke-BobiverseHarvest|Session summary:")
_HARVEST_RECEIPT_STATUS_RE = re.compile(
    r"(?i)\b(?:GIVEUP|SKIP|self-MRB|twin|DONE|PASS|FAIL)\b|\bduplicate of\b"
)
# FR #628 / FR #2670: chair-spam records (re-offer / drain loops) are never real FR work.
# Bare ``CRITICAL:`` without via-intake / feature-request is still spam (seat loop filings).
# Via-intake / feature-request ``CRITICAL:`` product filings are offerable (deadlock fix #2670).
CRITICAL_SPAM_PREFIX_RE = re.compile(r"(?i)^CRITICAL:")
CRITICAL_SPAM_SHAPE_RE = re.compile(
    r"(?i)\bdrain FR-unaccepted\b|\b\d+(st|nd|rd|th)\+? re-offer\b"
)
# Back-compat for tests/importers that still match the combined name.
CRITICAL_SPAM_TITLE_RE = re.compile(
    r"(?i)^CRITICAL:|\bdrain FR-unaccepted\b|\b\d+(st|nd|rd|th)\+? re-offer\b"
)
# FR #133 / bobiverse#258: evergreen MRB-home boards are not FR jobs.
EVERGREEN_MRB_HOME_TITLE_RE = re.compile(
    r"(?i)\bMRB\s+home\b|\bHostile\s+MRB\s+home\b|\bMRB:\s+\S+.*\bhandoff\b",
)
# FR #2562 / #2677 / #2687: MRB FAIL:/PASS: (or dash) verdict board titles are never FR jobs.
# FR #3299: MOVED owner/repo#N boards are also verdicts (done, not mrb-fail / not re-offered as FR).
# FR #3317: CLOSED not-useful (light harvest triage) is also a done verdict.
MRB_VERDICT_TITLE_RE = re.compile(r"(?i)^MRB\s+(FAIL|PASS|MOVED|CLOSED)\s*[-:]")
# FR #3658 / #3317: intake hold issues titled ``harvest: hold for <owner/repo> - …``
# must never be offered as FR even when the ``owner-missing`` label failed to apply
# (gh_filer retries create without labels when a label is missing on the repo).
# Carve-out from FR #1682 (plain ``harvest:`` promote titles stay offerable).
HARVEST_OWNER_MISSING_HOLD_TITLE_RE = re.compile(
    r"(?i)^harvest:\s*hold\s+for\b"
)
# bobiverse#224 / #765 / #781: FAIL-fix PRs (fix(mrb-N) / mrb-N-fix) are not MRB/UAT targets.
_MRB_FIX_TITLE_RE = re.compile(
    r"(?i)(?:^|\b)(?:fix\s*\(\s*mrb[-_]?\d+|mrb[-_]?\d+[-_]fix\b)"
)
SKIP_FR_LABELS = frozenset(
    {
        # FR #1682 / #1684 / operator 2026-10-04: skill is offerable (promote PR /
        # consolidate-by-book). Kept out of this set so intake harvests are handed out.
        # Still excluded from repo-UAT blocking via issue_blocks_repo_uat.
        "umbrella",
        "parent-fr",
        "mrb-home",
        "mrb_home",
        "evergreen",
        "evergreen-mrb",
        # FR #595: verdict / board labels are not implementable FRs.
        # FR #2562 / #2677: reverse #2464 — mrb-fail / mrb_fail are verdict boards,
        # never offerable FRs (remediation belongs on child product FRs).
        "mrb",
        "mrb-pass",
        "mrb-fail",
        "mrb_pass",
        "mrb_fail",
        # FR #628: held for a human / ionos / release gate.
        "needs-human",
        # needs-mrb1 must NOT be a SKIP_FR label (#1080/#1122/#1174 / PR #1236): that
        # emptied bobiverse offers under focus.strict and dropped rows on resync.
        # Operator 2026-10-04: needs-mrb1 is a hallucination — do not offer-block on it
        # (row_awaits_mrb1 always False). Intake no longer stamps the label.
        "blocked",
        "release-gate",
        # FR #3317: harvest tip held until the intended product repo exists.
        "owner-missing",
    }
)

# Labels safe to detect in free text (title/line/body). Bare ``mrb`` is labels-only ΓÇö
# otherwise titles like "harden MRB/FR routing" (#595) would false-positive.
SKIP_FR_LABELS_IN_TEXT = frozenset(
    lab
    for lab in SKIP_FR_LABELS
    if lab not in {"mrb", "needs-human", "blocked", "release-gate"}
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
    # Lesson PRs: refs are citations, not implementation links; author = opener seat.
    harvest_lesson: bool = False
    opened_by: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root(home: Path) -> Path:
    return bobreport.fleet_digest_home(Path(home))


@contextmanager
def _scoped_digest_home(home: Path | None):
    """Temporarily point ``BOB_DIGEST_HOME`` at ``home`` for token lookup, then restore.

    FR #2540: ``os.environ.setdefault("BOB_DIGEST_HOME", …)`` leaked the first caller's
    home for the rest of the process. ``fleet_digest_home`` / ``queue_path`` then redirected
    every later test or seat onto that home (GET /bob/v1/report after FR #2458 was enough).
    """
    if home is None:
        yield
        return
    key = "BOB_DIGEST_HOME"
    prev = os.environ.get(key)
    os.environ[key] = str(home)
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


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
    # GIT issues repo opened #N title by user ΓÇö title is mid tokens
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
    """One PM line: ``#1 FR owner/repo#n 2h titleΓÇª`` (title truncated only)."""
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
            title = cut + "ΓÇª"
        line = f"{head} {title}"
    else:
        line = head
    # hard cap (should already fit)
    while len(line.encode("utf-8")) > line_max and len(line) > 1:
        line = line[:-2] + "ΓÇª"
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
    # single job: no summary spam ΓÇö just the job line
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
    """Parse a Jeeves `GIT ΓÇª` line. None for ping, push, and other noise."""
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



def canonical_queue_repo(repo: str) -> str:
    """FR #785: map archived/legacy repos to their live successor (identity otherwise)."""
    key = (repo or "").strip()
    if not key:
        return key
    return ARCHIVED_REPO_SUCCESSORS.get(key.lower(), key)


def repo_archived_for_queue(repo: str, *, payload: dict | None = None) -> bool:
    """FR #785: True when the repo is a known archived source or the payload marks it archived."""
    key = (repo or "").strip()
    if key and key.lower() in ARCHIVED_REPO_SUCCESSORS:
        return True
    if isinstance(payload, dict):
        blob = payload.get("repository")
        if isinstance(blob, dict) and blob.get("archived"):
            return True
    return False


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


def is_harvest_lesson_pr(
    *,
    title: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> bool:
    """True for a ``harvest-lesson`` / ``lesson(<book>):`` skill-book PR (FR #2705)."""
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    if "harvest-lesson" in labs:
        return True
    return bool(re.match(r"(?i)^lesson\s*\(", (title or "").strip()))


_LESSON_OPENER_SEAT_RE = re.compile(r"(?i)\b(?:seat|agent)=`(?P<nick>[A-Za-z0-9_.-]+)`")


def lesson_pr_opener_seat(body: str = "") -> str:
    """Seat nick that opened a lesson PR, from the intake provenance footer (``seat=`` / ``agent=``).

    A lesson PR's author is whoever opened it. The seats that implemented an FR the
    lesson merely cites are not its authors. Returns '' when no seat nick is named
    (operator / audit PRs, ``agent=`Invoke-BobiverseHarvest``` without ``seat=``).
    """
    for m in _LESSON_OPENER_SEAT_RE.finditer(body or ""):
        nick = m.group("nick")
        if bobreport.parse_seat_nick(nick):
            return canonical_worker_nick(nick) or nick
    return ""


def _heal_lesson_mrb_row(row: dict, opener: str) -> None:
    """Lesson MRB row: drop cited-FR refs and any author stamp that is not the opener."""
    row.pop("refs", None)
    for k in ("author_seat", "implementer_seat", "author_nick", "author", "author_seats"):
        row.pop(k, None)
    if opener:
        row["author_seat"] = opener
        row["implementer_seat"] = opener


def is_intake_harvest_receipt_pr(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
) -> bool:
    """True when a pull is an intake harvest/skill receipt, not shop MRB work (FR #2650).

    Matches GhCliFiler drafts: ``harvest:`` / ``skill`` title plus ``via-intake``+``skill``
    labels, ``Invoke-BobiverseHarvest`` / ``Session summary:`` footer, or a receipt
    status word (DONE/PASS/FAIL/GIVEUP/SKIP/twin/…). Real worker promote PRs lack
    ``via-intake`` and receipt-status titles.

    FR #2705: ``harvest-lesson`` / ``lesson(<book>):`` skill-book PRs are offerable MRB
    work — never treated as receipts.
    """
    title_s = (title or "").strip()
    body_s = body or ""
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    if "harvest-lesson" in labs:
        return False
    if re.match(r"(?i)^lesson\s*\(", title_s):
        return False
    harvestish = bool(HARVEST_TITLE_RE.match(title_s))
    via_intake_skill = "via-intake" in labs and "skill" in labs
    if via_intake_skill and (harvestish or _INTAKE_HARVEST_FOOTER_RE.search(body_s)):
        return True
    if harvestish and _INTAKE_HARVEST_FOOTER_RE.search(body_s):
        return True
    if harvestish and _HARVEST_RECEIPT_STATUS_RE.search(title_s):
        return True
    return False



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
    # FR #2562 / #2677: reverse #2464 — do not drop bare `mrb` when mrb-fail is present.
    if hit:
        return f"label:{sorted(hit)[0]}"
    title_s = (title or "").strip()
    # FR #3658 / #3317: owner-missing hold titles (even with empty labels).
    if HARVEST_OWNER_MISSING_HOLD_TITLE_RE.search(title_s):
        return "owner_missing_hold_title"
    # FR #1682 / #1684: harvest:/skill: titles are offerable promote jobs (workers
    # consolidate by skill book then open a harvest/* PR). Do not SKIP_FR them —
    # except the hold-title carve-out above.
    # FR #628 / #2670: drain / Nth re-offer shapes are always spam.
    if CRITICAL_SPAM_SHAPE_RE.search(title_s):
        return "critical_spam_title"
    # FR #2670: via-intake / feature-request CRITICAL: is real work (must queue +
    # block UAT). Bare CRITICAL: without those labels stays SKIP_FR (seat spam).
    if CRITICAL_SPAM_PREFIX_RE.search(title_s):
        if "via-intake" not in labs and "feature-request" not in labs:
            return "critical_spam_title"
    # FR #2562 / #2677: MRB FAIL:/PASS: verdict board titles are never FR jobs.
    if MRB_VERDICT_TITLE_RE.search(title_s):
        return "mrb_verdict_title"
    blob = f"{title_s}\n{body or ''}"
    if SAFE_TO_CLOSE_RE.search(blob):
        return "safe_to_close"
    # FR #2480: exact fomprep MRB-home board signature in body (not generic "MRB home" prose).
    if _MRB_HOME_BOARD_BODY_RE.search(body or ""):
        return "mrb_home_board_body"
    # bobiverse#258 / FR #133 / FR #987: evergreen MRB-home boards by title shape only
    # (label mrb-home/evergreen already returned above). Do not scan the body ΓÇö real FRs
    # that mention "MRB home" in prose must stay assignable.
    if EVERGREEN_MRB_HOME_TITLE_RE.search(title_s):
        return "evergreen_mrb_home"
    # FR #595 / MRB #603 / FR #987: legacy queue rows may only put board labels in
    # title/line text (empty labels). Never run this scan when GitHub/labels are present
    # (false-positive on titles like "skip for stale mrb-home rows" / bodies saying
    # "evergreen"). Title/line only ΓÇö never the body.
    if not labs:
        title_l = title_s.lower()
        text_hits = []
        for lab in sorted(SKIP_FR_LABELS_IN_TEXT, key=len, reverse=True):
            if re.search(rf"(?<![a-z0-9]){re.escape(lab)}(?![a-z0-9])", title_l):
                text_hits.append(lab)
        if text_hits:
            return f"label_text:{text_hits[0]}"
    # FR #1812: via-intake+skill "PR opened" / pull URL summaries are receipts of an
    # already-open harvest PR — do not enqueue as FR work (workers would re-implement).
    if "via-intake" in labs and "skill" in labs:
        if re.search(r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+", blob, re.I):
            return "harvest_pr_summary"
        if re.search(r"(?i)\bPR\s+opened\b", title_s):
            return "harvest_pr_summary"
    return None


def row_skip_fr_reason(row: dict) -> str | None:
    labels = row.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    repo = str(row.get("repo") or "").strip().lower()
    ident = _norm_row_id(row.get("id"))
    if repo and ident and (repo, ident) in _SKIP_FR_ISSUE_PINS:
        return "hard_pin_umbrella"
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


def row_on_cooldown(row: dict, now: float, nick: str = "") -> bool:
    """True when this seat must wait out ``cooldown_until``.

    Global row cooldown after GIVEUP used to block *every* seat for
    ``GIVEUP_COOLDOWN_S``, which left the fleet idle while other live seats
    could have taken the work. Ledger / ``giveup_seats`` already prevent
    re-offer to the giver; other seats skip the global wait.
    Compare seats via ``canonical_worker_nick`` so ``w-io-<pid>`` matches
    ``win-mpre8vi4u6u-<pid>`` stored after GIVEUP.
    """
    until = _parse_iso_ts(str(row.get("cooldown_until") or ""))
    if until is None or float(now) >= until:
        return False
    me = (nick or "").strip()
    if not me:
        return True
    seats = giveup_seat_set(row)
    if seats and not nick_in_giveup_seats(row, me):
        return False
    return True


def row_needs_human(row: dict, nick: str = "") -> bool:
    """True when this seat must not take a needs_human row.

    After GIVEUP loops the chair stamps ``needs_human`` *and* ``giveup_seats``.
    Early GIVEUPs stay per-seat (FR #1236 / #1407) so one machine's GIVEUP does not
    idle the fleet. FR #3277: when ``giveup_seats`` is set, only those seats are
    blocked — even after ``giveup_count`` reaches ``GIVEUP_NEEDS_HUMAN_COUNT`` —
    so a self-MRB author's GIVEUPs cannot strand every other seat. A bare
    ``needs_human`` with no giveup_seats stays a global human/vision gate.
    Seat match is canonical (``w-io-*`` == ``win-mpre8vi4u6u-*``).
    """
    v = row.get("needs_human")
    if isinstance(v, bool):
        flag = v
    else:
        flag = str(v or "").strip().lower() in ("1", "true", "yes")
    if not flag:
        return False
    seats = giveup_seat_set(row)
    me = (nick or "").strip()
    # FR #3277 / #1236: giveup_seats is the seat-scoped gate; do not let a high
    # giveup_count short-circuit into a fleet-wide block when seats are listed.
    if seats:
        if me:
            return nick_in_giveup_seats(row, me)
        return True
    try:
        giveups = int(row.get("giveup_count") or 0)
    except (TypeError, ValueError):
        giveups = 0
    if giveups >= GIVEUP_NEEDS_HUMAN_COUNT:
        return True
    return True


def row_awaits_mrb1(row: dict) -> bool:
    """Legacy FR #1363 offer gate — always False (operator 2026-10-04).

    ``needs-mrb1`` was an intake hallucination that stranded ungated work while
    open-issue counts climbed. Kept as a named helper so call sites/tests stay
    stable; label presence must not block ``!bored`` / ``!assign`` offers.
    """
    return False


def issue_blocks_repo_uat(
    *,
    title: str = "",
    body: str = "",
    labels: tuple[str, ...] | list[str] = (),
    state: str = "",
) -> bool:
    """True when an open issue must hold repo-level UAT back (t853u / FR #1416).

    ``needs-mrb1`` must not prevent repo UAT (#1416) and must not block offers
    (operator 2026-10-04: label is a hallucination). Kept as a non-blocking
    open-issue class for UAT clearance only.

    FR #1682 / #1684: skill / harvest: / skill: receipts are offerable
    promote jobs but must not hold repo UAT (honesty-box backlog is not product work).

    FR #2971: ``feature-request`` (incl. via-intake product FRs) always blocks UAT.
    Do not treat a prose title that merely starts with the word ``Harvest`` /
    ``Skill`` as a harvest receipt — require ``harvest:`` / ``skill:`` (colon) or
    the ``skill`` label. Live miss: #2970 title ``Harvest re-promotes…`` left the
    repo "clear" and UAT #0 was offered.
    """
    if issue_skip_fr_reason(title=title, body=body, labels=labels, state=state):
        return False
    labs = {str(x).strip().lower() for x in (labels or []) if str(x).strip()}
    if "needs-mrb1" in labs:
        return False
    # Ordinary product FRs — including via-intake — block UAT even if the title
    # starts with the word Harvest/Skill (FR #2971).
    if "feature-request" in labs:
        return True
    if "skill" in labs:
        return False
    title_s = (title or "").strip()
    # Receipt titles only: "harvest: …" / "skill: …", not "Harvest re-promotes…".
    if re.match(r"(?i)^(harvest|skill)\s*:", title_s):
        return False
    if HARVEST_TITLE_RE.match(title_s) and "via-intake" not in labs:
        return False
    return True


# FR #587: machine-affinity for seats that cannot do the work (WP0 live / chair-outbox).
# FR #628 / #732: also accept bare ``machine:<id>`` (legacy pin label).
_REQUIRE_MACHINE_LABEL_RE = re.compile(
    r"(?i)^(?:needs|require[_-]?machine|machine)[-_:=]([a-z0-9][a-z0-9_.-]*)$"
)
# Tokens that match needs-<x> but are human/process gates, not fleet machine ids.
# needs-mrb1 was wrongly stamped require_machine=mrb1 and stranded the offer queue (#1080).
_REQUIRE_MACHINE_NON_MACHINE = frozenset(
    {
        "mrb1",
        "mrb",
        "human",
        "vision",
        "blocked",
        "release",
        "release-gate",
        "gate",
    }
)
# Explicit cue -> fleet machine id (normalized lowercase).
# FR #1508: title/label cues vs body cues. Bare machine names / require_machine=
# in an issue body often appear as evidence about *other* pins and must not
# re-pin the filing itself (#1507 class).
# FR #1824 / #1843: a *dedicated body line* ``require_machine: ionos`` (or ``=``)
# is an intentional pin — honor it. Inline evidence prose still must not pin.
_REQUIRE_MACHINE_TITLE_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\bce-priority-dev1\b"), "ce-priority-dev1"),
    (re.compile(r"(?i)\bce-priority-dev\b"), "ce-priority-dev1"),
    (re.compile(r"(?i)\brequire_machine\s*=\s*ce-priority-dev1\b"), "ce-priority-dev1"),
    (re.compile(r"(?i)\brequire_machine\s*=\s*ionos\b"), "ionos"),
    (re.compile(r"(?i)\bneeds-ionos\b"), "ionos"),
    (re.compile(r"(?i)\bchair[- ]outbox\b"), "ionos"),
    # FR #1550: monitor idle+ungated / ircJeeves StartPending filings are chair-host ops
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,60}\bstartpending\b"), "ionos"),
    (re.compile(r"(?i)\bstartpending\b.{0,60}\b(?:irc)?jeeves\b"), "ionos"),
    (re.compile(r"(?i)\bidle seats?\b.{0,120}\bungated offerable\b"), "ionos"),
    (re.compile(r"(?i)\bungated offerable\b.{0,120}\bidle seats?\b"), "ionos"),
    # FR #1899: title-level intake/BobCallback 502 ops filings
    (re.compile(r"(?i)\bintake\b.{0,40}\b(?:BobCallback|ARR)\b.{0,40}\b502\b"), "ionos"),
    (re.compile(r"(?i)\b(?:BobCallback|ARR)\b.{0,40}\bintake\b.{0,40}\b502\b"), "ionos"),
    (re.compile(r"(?i)\bintake\b.{0,60}\b502\b.{0,40}\b(?:Bad Gateway|harvest)"), "ionos"),
    # FR #2451: release pack titles that say install/smoke on ionos
    (re.compile(r"(?i)\binstall(?:\s*\+\s*smoke|\+smoke)?\s+on\s+ionos\b"), "ionos"),
    # FR #3129: Sync/compose ircJeeves on ionos (allowlist / intake 403 class of #3122)
    (re.compile(r"(?i)\bionos\b.{0,80}\b(?:sync(?:/compose)?|compose)\b.{0,80}\b(?:irc)?jeeves\b"), "ionos"),
    (re.compile(r"(?i)\b(?:sync(?:/compose)?|compose)\b.{0,80}\b(?:irc)?jeeves\b.{0,40}\bionos\b"), "ionos"),
    (re.compile(r"(?i)\bSync-BobiverseFromRepo\b.{0,80}\b(?:irc)?jeeves\b"), "ionos"),
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,80}\bSync-BobiverseFromRepo\b"), "ionos"),
)
_REQUIRE_MACHINE_BODY_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    # FR #1824: dedicated pin line only (MULTILINE). Do not match inline evidence.
    (re.compile(r"(?im)^\s*[`*]*require_machine\s*[:=]\s*ionos\b"), "ionos"),
    (re.compile(r"(?im)^\s*[`*]*require_machine\s*[:=]\s*ce-priority-dev1\b"), "ce-priority-dev1"),
    (re.compile(r"(?im)^\s*[`*]*require_machine\s*[:=]\s*ce-priority-dev\b"), "ce-priority-dev1"),
    (re.compile(r"(?im)^\s*[`*]*require_machine\s*[:=]\s*flamingo\b"), "flamingo"),
    (re.compile(r"(?im)^\s*[`*]*require_machine\s*[:=]\s*marchhare\b"), "marchhare"),
    # agentic_fomprep WP0 live proof must run on DEV1
    (re.compile(r"(?i)PRIORITY_WP0_INSTANCE\s*=\s*ce-priority-dev"), "ce-priority-dev1"),
    (re.compile(r"(?i)\bWP0\s+live\b"), "ce-priority-dev1"),
    (re.compile(r"(?i)\bAllowedComputer\s*[:=]\s*CE-PRIORITY-DEV1\b"), "ce-priority-dev1"),
    # FR #852: recycle/recompose live ircJeeves / prune chair queue on ionos
    (re.compile(r"(?i)\b(?:recycle|recompose)\b.{0,60}\b(?:irc)?jeeves\b"), "ionos"),
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,60}\b(?:recycle|recompose|recycled)\b"), "ionos"),
    # FR #3129: Sync/compose (or Sync-BobiverseFromRepo) ircJeeves on ionos.
    # Do not bare-match Sync-BobiverseFromRepo alone (bob/airc Sync on any fleet box).
    (re.compile(r"(?i)\b(?:sync(?:/compose)?|compose)\b.{0,80}\b(?:irc)?jeeves\b"), "ionos"),
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,80}\b(?:sync(?:/compose)?|compose)\b"), "ionos"),
    (re.compile(r"(?i)\bSync-BobiverseFromRepo\b.{0,80}\b(?:irc)?jeeves\b"), "ionos"),
    (re.compile(r"(?i)\b(?:irc)?jeeves\b.{0,80}\bSync-BobiverseFromRepo\b"), "ionos"),
    (re.compile(r"(?i)\bOn\s+ionos\s*:\s*Sync-BobiverseFromRepo\b"), "ionos"),
    (re.compile(r"(?i)\bprune\b.{0,80}\bqueue\.json\b"), "ionos"),
    (re.compile(r"(?i)\bqueue\.json\b.{0,80}\b(?:prune|on\s+ionos)\b"), "ionos"),
    # FR #1363: BobCallback principal / SYSTEM vs Admin .bobiverse lives on the chair host
    (re.compile(r"(?i)\bBobCallback\b.{0,120}\bSYSTEM\b"), "ionos"),
    (re.compile(r"(?i)\bSYSTEM\b.{0,120}\bBobCallback\b"), "ionos"),
    (re.compile(r"(?i)\bBobCallback\b.{0,160}\.bobiverse\b"), "ionos"),
    (re.compile(r"(?i)\bBobCallback\b.{0,80}\bprincipal\b"), "ionos"),
    # FR #1550 / #1559: monitor check evidence / missing shop OFFER after StartPending.
    # Bare Invoke-JeevesMonitorCheck alone is too broad (docs/skills); require ops context.
    (re.compile(
        r"(?i)\bInvoke-JeevesMonitorCheck\b.{0,200}\b(?:idle_seats|StartPending|offerable|no shop OFFER)\b"
    ), "ionos"),
    (re.compile(
        r"(?i)\b(?:idle_seats|StartPending|offerable|no shop OFFER)\b.{0,200}\bInvoke-JeevesMonitorCheck\b"
    ), "ionos"),
    (re.compile(r"(?i)\bno shop OFFER\b"), "ionos"),
    (re.compile(r"(?i)\bchair[- ]outbox\b.{0,100}\b(?:OFFER|!bored|GIT announce)"), "ionos"),
    # FR #1899: intake/ARR/BobCallback 502 ops live on the Ergo/chair host (not flamingo)
    (re.compile(r"(?i)\b(?:intake|/bob/v1/intake)\b.{0,140}\b(?:502|Bad Gateway)\b"), "ionos"),
    (re.compile(r"(?i)\b(?:502|Bad Gateway)\b.{0,140}\b(?:intake|/bob/v1/intake|BobCallback|harvest-outbox)\b"), "ionos"),
    # FR #3610: outage/ops wording only — bare :7700 or LISTEN in design prose
    # (e.g. Hours webhook FR #3450 "BobCallback (default 127.0.0.1:7700)") must not pin.
    (re.compile(
        r"(?i)\bBobCallback\b.{0,160}\b(?:502|Bad Gateway|DOWN|not[- ]listening|no LISTEN|restart|recycle)\b"
    ), "ionos"),
    (re.compile(
        r"(?i)\b(?:502|Bad Gateway|DOWN|not[- ]listening|no LISTEN|restart|recycle)\b.{0,160}\bBobCallback\b"
    ), "ionos"),
    (re.compile(r"(?i)\b(?:ARR|reverse[- ]proxy)\b.{0,140}\b(?:intake|BobCallback|/bob/v1)\b"), "ionos"),
    (re.compile(r"(?i)\b(?:intake|BobCallback|/bob/v1)\b.{0,140}\b(?:ARR|reverse[- ]proxy)\b"), "ionos"),
    (re.compile(r"(?i)\bharvest-outbox\b.{0,100}\b(?:502|Bad Gateway|KEPT)\b"), "ionos"),
    # FR #2451: release pack FRs that install/smoke on ionos (not bare release-out)
    (re.compile(r"(?i)\binstall(?:\s*\+\s*smoke|\+smoke)?\s+on\s+ionos\b"), "ionos"),
    (re.compile(r"(?i)\bsmoke\s+on\s+ionos\b"), "ionos"),
    # FR #2512: Pack-Airc / Pack-BobiverseRelease -Product airc near Assert or ionos install/smoke
    (re.compile(
        r"(?i)\bPack-Airc\b.{0,220}\b(?:Assert-ReleaseAssets|install(?:\s*\+\s*smoke|\+smoke)?\s+on\s+ionos)\b"
    ), "ionos"),
    (re.compile(
        r"(?i)\bPack-BobiverseRelease\b.{0,160}\b-Product\s+airc\b.{0,160}\b(?:Assert-ReleaseAssets|install(?:\s*\+\s*smoke|\+smoke)?\s+on\s+ionos)\b"
    ), "ionos"),
)
# Back-compat for tests importing the combined name.
_REQUIRE_MACHINE_CUES: tuple[tuple[re.Pattern[str], str], ...] = (
    _REQUIRE_MACHINE_TITLE_CUES + _REQUIRE_MACHINE_BODY_CUES
)

# Hard pins for known WP0 / machine-gated issues (FR #1093): survive empty title/body on stale rows.
_REQUIRE_MACHINE_ISSUE_PINS: dict[tuple[str, str], str] = {
    ("simonbarnett/agentic_fomprep", "#56"): "ce-priority-dev1",
    # FR #2312 / #1714: ionos orphan workers-map / nak-busy — body pin is past the
    # historic body[:500] truncate window; hard pin so marchhare never gets the offer.
    ("simonbarnett/bobiverse", "#1714"): "ionos",
    # FR #2512 / #2511: airc MSI re-pack + install/smoke on ionos (mis-offered to marchhare
    # while frozen jeeves lagged #2451 cues). Hard pin survives empty/stale queue body.
    ("simonbarnett/bobiverse", "#2511"): "ionos",
    # FR #2525 / #2522: maintenance butler FR pin past truncate + backtick line.
    ("simonbarnett/bobiverse", "#2522"): "ionos",
    # FR #3129 / #3122: ionos Sync/compose ircJeeves for intake allowlist (mis-offered to marchhare).
    ("simonbarnett/bobiverse", "#3122"): "ionos",
}

# FR #2480 / #2471 / #2472: agentic_fomprep evergreen umbrella / MRB-home boards.
# Labels mrb-home/umbrella/parent-fr should SKIP_FR (#271), but stale queue rows
# enqueued before labels (or when API label payloads were empty) kept being offered.
# Hard-pin by (repo, #N) so resync/offer always prune.
# FR #2562 / #2677: reverse #2521 — re-pin #11 (MRB FAIL verdict board). Remediation
# belongs on child FRs (#9/#10), never on the verdict board itself.
_SKIP_FR_ISSUE_PINS: set[tuple[str, str]] = {
    ("simonbarnett/agentic_fomprep", "#3"),
    ("simonbarnett/agentic_fomprep", "#7"),
    ("simonbarnett/agentic_fomprep", "#8"),
    ("simonbarnett/agentic_fomprep", "#9"),
    ("simonbarnett/agentic_fomprep", "#11"),
    ("simonbarnett/agentic_fomprep", "#20"),
}

# Exact board phrase used by fomprep MRB-home intake issues (body). Title-only
# evergreen regex (#987) deliberately ignores body "MRB home" prose; this phrase
# is the parked-board signature and is safe to skip.
_MRB_HOME_BOARD_BODY_RE = re.compile(
    r"(?i)This issue is the MRB home for (?:that|this) feature request"
)

# Queue rows keep a short body for size; trailing dedicated require_machine pins must
# survive (FR #2312 — #1714 pin sat after char 500 and was dropped on enqueue).
QUEUE_BODY_LIMIT = 500
_REQUIRE_MACHINE_PIN_LINE_RE = re.compile(
    # FR #2525: allow markdown wrappers + trailing notes, e.g.
    # `` `require_machine: ionos` (hotpatch verify) ``
    r"(?im)^[ \t]*[`*]*require_machine\s*[:=]\s*([a-z0-9][a-z0-9_.-]*)\b[`*]*"
)


def _body_for_queue(body: str, *, limit: int | None = None) -> str:
    """Store issue/PR body for queue rows without dropping require_machine pin lines."""
    text = str(body or "")
    lim = QUEUE_BODY_LIMIT if limit is None else int(limit)
    if lim < 1:
        lim = QUEUE_BODY_LIMIT
    if len(text) <= lim:
        return text
    pins: list[str] = []
    for m in _REQUIRE_MACHINE_PIN_LINE_RE.finditer(text):
        mid = (m.group(1) or "").strip().lower()
        if not mid:
            continue
        line = f"require_machine: {mid}"
        if line not in pins:
            pins.append(line)
    head = text[:lim].rstrip()
    if not pins:
        return head
    # Prefer pins that are not already intact inside the head window.
    missing = [p for p in pins if p not in head]
    if not missing:
        return head
    return head + "\n" + "\n".join(missing)


def infer_require_machine(
    *,
    title: str = "",
    body: str = "",
    labels=(),
    line: str = "",
    repo: str = "",
    ident: str = "",
) -> str:
    """Return a fleet machine id the job must run on, or '' (FR #587).

    Labels ``needs-<machine>`` / ``require_machine:<machine>`` win first, then
    title/body/line cues (dedicated body ``require_machine:``/``=`` pin lines; WP0 live -> ce-priority-dev1; needs-ionos / chair-outbox /
    recycle|recompose|Sync/compose Jeeves / Sync-BobiverseFromRepo near Jeeves / prune queue.json / install(+smoke) on ionos -> ionos;
    FR #587 / #852 / #2451 / #3129).
    """
    labs = labels or ()
    if isinstance(labs, str):
        labs = [labs]
    repo_l = str(repo or "").strip().lower()
    id_l = str(ident or "").strip()
    if id_l and not id_l.startswith("#"):
        id_l = f"#{id_l}"
    pin = _REQUIRE_MACHINE_ISSUE_PINS.get((repo_l, id_l))
    if pin:
        return pin
    for lab in labs:
        s = str(lab or "").strip()
        m = _REQUIRE_MACHINE_LABEL_RE.match(s)
        if m:
            mid = bobreport.normalize_machine_id(m.group(1)) or m.group(1).strip().lower()
            if mid and mid not in _REQUIRE_MACHINE_NON_MACHINE:
                return mid
        # bare needs-ionos style already covered by cue regex below via label join
    # Title + labels + assign line: bare machine / require_machine= cues (FR #1508).
    title_blob = "\n".join(
        [
            str(title or ""),
            str(line or ""),
            " ".join(str(x) for x in labs),
        ]
    )
    for rx, mid in _REQUIRE_MACHINE_TITLE_CUES:
        if rx.search(title_blob):
            return mid
    # Body: only strong WP0 / ionos-ops cues (not bare machine name mentions).
    body_blob = str(body or "")
    for rx, mid in _REQUIRE_MACHINE_BODY_CUES:
        if rx.search(body_blob) or rx.search(title_blob):
            return mid
    return ""


def row_require_machine(row: dict) -> str:
    """Machine id required for this queue row, if any (FR #587 / #1093)."""
    # Hard issue pins win over unpin tokens (any/none) — FR #1093 WP0 must not leak
    # back to win-mpre after a monitor ``require_machine=any`` clear.
    hard = infer_require_machine(
        title="",
        body="",
        labels=(),
        line="",
        repo=str(row.get("repo") or ""),
        ident=str(row.get("id") or ""),
    )
    if hard:
        return hard
    stamped = str(row.get("require_machine") or "").strip().lower()
    # Operator/monitor unpin: "*" / "any" / "none" means do not re-infer from title/body
    # (titles that mention require_machine=ce-priority-dev1 were re-pinning forever).
    if stamped in {"*", "any", "none", "-"}:
        return ""
    if stamped:
        mid = bobreport.normalize_machine_id(stamped) or stamped
        # Ignore corrupt stamps like mrb1 from needs-mrb1 (#1080).
        if mid and mid not in _REQUIRE_MACHINE_NON_MACHINE:
            return mid
    labels = row.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    return infer_require_machine(
        title=str(row.get("title") or ""),
        body=str(row.get("body") or ""),
        labels=tuple(str(x) for x in labels),
        line=str(row.get("line") or ""),
        repo=str(row.get("repo") or ""),
        ident=str(row.get("id") or ""),
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

    issues opened/reopened -> FR (skipped for skill/harvest/safe-to-close/umbrella/closed ΓÇö FR #180)
    pull_request opened/ready_for_review -> MRB (with refs to linked issues)
    pull_request closed -> MRB row used for supersede (merged flag set)
    issues closed -> FR/UAT removal via apply_queue_event (task FR id)
    issues/pull_request labeled|unlabeled -> update matching row labels; re-eval FR skip (FR #3275)
    """
    if not isinstance(payload, dict):
        return None
    ev = (event or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()
    repo = _payload_repo(payload)
    if not repo or not REPO_RE.fullmatch(repo):
        return None
    src = (line or "").strip()
    # FR #785: never enqueue new work from an archived repo (closed still flows for prune).
    enqueue_action = action in ("opened", "reopened", "ready_for_review", "edited")
    if enqueue_action and repo_archived_for_queue(repo, payload=payload):
        return None

    if ev == "issues" and action in ("opened", "reopened"):
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        issue = _issue_blob(payload)
        # FR #838 / #846: issue payloads for pulls include ``pull_request`` ΓÇö never FR.
        if issue.get("pull_request"):
            return None
        title = str(issue.get("title") or "")
        body = str(issue.get("body") or "")
        labels = _label_names(issue.get("labels"))
        state = str(issue.get("state") or "open")
        # FR #180 / #2340: closed issues must never become FR rows (opened/reopened
        # with state=closed, or backfill synthesising opened for a closed issue).
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

    # FR #3275: labeled/unlabeled mutate queue labels in place (zero REST).
    if ev in ("issues", "pull_request") and action in ("labeled", "unlabeled"):
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        blob = _issue_blob(payload) if ev == "issues" else _pr_blob(payload)
        if ev == "issues" and blob.get("pull_request"):
            return None
        title = str(blob.get("title") or "")
        body = str(blob.get("body") or "")
        labels = _label_names(blob.get("labels"))
        state = str(blob.get("state") or "open")
        task = "FR" if ev == "issues" else "MRB"
        return GitClaim(
            repo=repo,
            task=task,
            id=ident,
            event=ev,
            action=action,
            line=src or title,
            title=title,
            body=body,
            labels=labels,
            state=state,
        )

    # FR #924: include synchronize so author_seat backfill runs on push without waiting for edited.
    if ev == "pull_request" and action in ("opened", "ready_for_review", "edited", "synchronize"):
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        pr = _pr_blob(payload)
        title = str(pr.get("title") or "")
        body = str(pr.get("body") or "")
        labels = _label_names(pr.get("labels"))
        # FR #2650 / #2604: draft PRs never become MRB (resync already skips drafts).
        # MRB #2651: also edited/synchronize — _apply_claim_to_doc appends unaccepted for those.
        if action in ("opened", "ready_for_review", "edited", "synchronize") and pr.get("draft") is True:
            return None
        # FR #2650 / MRB #2651: intake harvest receipt PRs never become MRB via webhook
        # (opened/ready_for_review/edited/synchronize all call _append_unaccepted).
        if action in ("opened", "ready_for_review", "edited", "synchronize") and is_intake_harvest_receipt_pr(
            title=title, body=body, labels=labels
        ):
            return None
        # bobiverse#224 / #781: FAIL-fix PRs never start a second MRB (open/ready only).
        if action in ("opened", "ready_for_review") and is_mrb_fix_pr_title(title):
            return None
        # Lesson PRs cite FRs; they do not implement them. No refs, so the cited FR's
        # implementer is not stamped as author and the FR row is not superseded.
        lesson = is_harvest_lesson_pr(title=title, labels=labels)
        refs = () if lesson else extract_closes_issue_ids(title, body, src, repo=repo)
        task = "MRB" if action in ("opened", "ready_for_review") else "MRB"
        return GitClaim(
            repo=repo,
            task=task,
            id=ident,
            event=ev,
            action=action,
            line=src,
            refs=refs,
            harvest_lesson=lesson,
            opened_by=lesson_pr_opener_seat(body) if lesson else "",
        )

    if ev == "pull_request" and action == "closed":
        ident = _payload_number(ev, payload)
        if ident is None:
            return None
        pr = _pr_blob(payload)
        title = str(pr.get("title") or "")
        body = str(pr.get("body") or "")
        labels = _label_names(pr.get("labels"))
        # Lesson PRs cite FRs: closing one (merged or not) must not touch or re-open them.
        # Never self-reference: the chair line "... closed #N ..." is not a link to FR #N.
        if is_harvest_lesson_pr(title=title, labels=labels):
            refs = ()
        else:
            refs = tuple(
                r for r in extract_closes_issue_ids(title, body, src, repo=repo) if r != ident
            )
        merged = bool(pr.get("merged"))
        return GitClaim(
            repo=repo,
            task="MRB",
            id=ident,
            event=ev,
            action=action,
            line=src or title,
            refs=refs,
            merged=merged,
            title=title,
            body=body,
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
    want_id = _norm_row_id(ident)
    want_tasks = {str(t).upper() for t in tasks}
    doc["unaccepted"] = [
        r
        for r in doc["unaccepted"]
        if not (
            str(r.get("repo") or "") == str(repo or "")
            and _norm_row_id(r.get("id")) == want_id
            and str(r.get("task") or "").upper() in want_tasks
        )
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


# FR #2623: citing DONE FR must not overwrite the true implementer on an existing MRB row.
_IMPLEMENTER_KEEP_KEYS = frozenset(
    {"author_seat", "implementer_seat", "author_nick", "author"}
)


def resolve_done_fr_implementer_seat(
    doc: dict,
    *,
    pr_repo: str,
    pr_id: str,
    issue_repo: str,
    issue_id: str,
    done_nick: str,
) -> str:
    """Seat to stamp as MRB implementer after a DONE FR with a pull URL (FR #2623).

    Prefer (1) an existing MRB row stamp for the pull, then (2) the earliest prior
    DONE FR that already pointed at the same pull (or same issue+pull). A re-offered
    FR whose DONE only cites another seat's open PR must keep that earlier
    implementer — never the citing seat.
    """
    want_pr = _norm_row_id(pr_id)
    for bucket in ("unaccepted", "accepted", "done"):
        for row in doc.get(bucket) or []:
            if str(row.get("task") or "").upper() != "MRB":
                continue
            if str(row.get("repo") or "") != str(pr_repo or ""):
                continue
            if _norm_row_id(row.get("id")) != want_pr:
                continue
            seat = str(
                row.get("implementer_seat")
                or row.get("author_seat")
                or row.get("author_nick")
                or ""
            ).strip()
            if seat and bobreport.parse_seat_nick(seat):
                return canonical_worker_nick(seat) or seat

    pull_num = str(pr_id or "").lstrip("#")
    pull_needle = f"/pull/{pull_num}"
    issue_norm = _norm_row_id(issue_id)
    for row in doc.get("done") or []:
        if str(row.get("task") or "").upper() != "FR":
            continue
        url = str(row.get("url") or row.get("result") or "")
        if pull_needle not in url:
            continue
        parsed = parse_github_pull_url(url)
        same_pull = bool(parsed and parsed[0] == pr_repo and _norm_row_id(parsed[1]) == want_pr)
        if not same_pull and pr_repo.lower() not in url.lower():
            continue
        same_issue = (
            str(row.get("repo") or "") == str(issue_repo or "")
            and _norm_row_id(row.get("id")) == issue_norm
        )
        if not (same_pull or same_issue):
            continue
        seat = str(row.get("nick") or row.get("done_by") or "").strip()
        if seat and bobreport.parse_seat_nick(seat):
            return canonical_worker_nick(seat) or seat

    nick = str(done_nick or "").strip()
    if nick and bobreport.parse_seat_nick(nick):
        return canonical_worker_nick(nick) or nick
    return nick


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
                if claim.action in ("labeled", "unlabeled") or claim.labels:
                    row["labels"] = list(claim.labels)
                if claim.state:
                    row["state"] = str(claim.state).strip().lower()
                for k, v in extra.items():
                    if not v:
                        continue
                    # FR #2623: keep the true implementer when a citing DONE refreshes the MRB.
                    if k in _IMPLEMENTER_KEEP_KEYS and str(row.get(k) or "").strip():
                        continue
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
        row["body"] = _body_for_queue(claim.body)
    if claim.labels:
        row["labels"] = list(claim.labels)
    # FR #2340: persist issue state so closed rows can be purged/skipped offline.
    if claim.state:
        row["state"] = str(claim.state).strip().lower()
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
    """FR #587 / #1093: persist require_machine on enqueue/refresh when cues match.

    Hard issue pins always overwrite empty/unpin tokens. A real machine stamp is kept.
    Operator unpin (``any`` / ``none`` / ``*`` / ``-``) must survive title/body cues that
    merely *mention* ``require_machine=ce-priority-dev1`` as evidence (e.g. #1116) —
    otherwise monitor clears are wiped on the next offer/resync stamp.
    """
    title = str((claim.title if claim else "") or row.get("title") or "")
    body = str((claim.body if claim else "") or row.get("body") or "")
    line = str((claim.line if claim else "") or row.get("line") or "")
    labels = list(claim.labels) if claim and claim.labels else (row.get("labels") or [])
    if isinstance(labels, str):
        labels = [labels]
    repo = str((claim.repo if claim else "") or row.get("repo") or "")
    ident = str((claim.id if claim else "") or row.get("id") or "")
    repo_l = repo.strip().lower()
    id_l = f"#{str(ident or '').strip().lstrip('#')}"
    hard = _REQUIRE_MACHINE_ISSUE_PINS.get((repo_l, id_l), "")
    stamped = str(row.get("require_machine") or "").strip().lower()
    if stamped in {"*", "any", "none", "-"}:
        if hard:
            row["require_machine"] = hard
        return
    if stamped:
        mid = bobreport.normalize_machine_id(stamped) or stamped
        if mid and mid not in _REQUIRE_MACHINE_NON_MACHINE:
            return
    req = infer_require_machine(
        title=title, body=body, labels=labels, line=line, repo=repo, ident=ident
    )
    if req:
        row["require_machine"] = req


def _apply_label_mutation(doc: dict, claim: GitClaim) -> str:
    """FR #3275: labeled/unlabeled update labels on matching rows; re-eval FR skip locally."""
    updated = False
    found_unaccepted = False
    for bucket in ("unaccepted", "accepted"):
        for row in doc.get(bucket) or []:
            if not isinstance(row, dict):
                continue
            if not _same(row, claim.repo, claim.task, claim.id):
                continue
            if bucket == "unaccepted":
                found_unaccepted = True
            row["labels"] = list(claim.labels)
            row["action"] = claim.action
            row["event"] = claim.event
            if claim.title:
                row["title"] = claim.title
            if claim.body:
                row["body"] = _body_for_queue(claim.body)
            if claim.state:
                row["state"] = str(claim.state).strip().lower()
            _stamp_require_machine(row, claim)
            updated = True

    if claim.task == "FR":
        skip = issue_skip_fr_reason(
            title=claim.title, body=claim.body, labels=claim.labels, state=claim.state
        )
        if skip:
            n = _remove_unaccepted(doc, claim.repo, "FR", claim.id)
            if n:
                return "removed"
            return "updated" if updated else "noop"
        if not found_unaccepted and not repo_archived_for_queue(claim.repo):
            ch = _append_unaccepted(doc, claim)
            if ch == "skipped":
                return "noop"
            if ch == "added":
                return "added"
            return "updated" if updated or ch == "duplicate" else "noop"
        return "updated" if updated else "noop"

    # MRB: mutate existing rows only (do not invent an MRB from a label event).
    return "updated" if updated else "noop"


def _apply_claim_to_doc(doc: dict, claim: GitClaim) -> str:
    """Mutate queue doc for one claim. Returns added|removed|updated|duplicate|noop|error."""
    if claim.task not in TASK_KINDS and claim.action not in (
        "closed",
        "edited",
        "labeled",
        "unlabeled",
    ):
        return "error"
    ev, action = claim.event, claim.action
    changed = "noop"

    if ev in ("issues", "pull_request") and action in ("labeled", "unlabeled"):
        return _apply_label_mutation(doc, claim)

    if ev == "issues" and action in ("opened", "reopened"):
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
        n = _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"FR", "PR"})
        before = len(doc["unaccepted"])
        doc["unaccepted"] = [
            r for r in doc["unaccepted"]
            if not (r.get("repo") == claim.repo and r.get("id") == claim.id and r.get("task") == "UAT"
                    and r.get("action") != "uat")
        ]
        n += before - len(doc["unaccepted"])
        changed = "removed" if n else "noop"

    elif ev == "pull_request" and action in (
        "opened",
        "ready_for_review",
        "edited",
        "synchronize",
    ):
        if claim.harvest_lesson:
            implementer = claim.opened_by  # lesson PR author = opener, never a cited FR's implementer
        else:
            implementer = fr_implementer_seat_from_doc(doc, claim.repo, claim.refs)
        for ref in claim.refs:
            _remove_unaccepted_tasks(doc, claim.repo, ref, {"FR", "PR", "UAT"})
        extra: dict[str, str] = {}
        if claim.refs:
            extra["refs"] = ",".join(claim.refs)
        extra["url"] = (
            f"https://github.com/{claim.repo}/pull/{str(claim.id).lstrip('#')}"
        )
        if implementer:
            extra["author_seat"] = implementer
            extra["implementer_seat"] = implementer
        changed = _append_unaccepted(doc, claim, **extra)
        for r in doc["unaccepted"]:
            if not _same(r, claim.repo, "MRB", claim.id):
                continue
            if not PULL_URL_RE.search(str(r.get("url") or "")):
                r["url"] = extra["url"]
            if claim.harvest_lesson:
                _heal_lesson_mrb_row(r, claim.opened_by)
            elif implementer and not row_author_seats(r):
                r["author_seat"] = implementer
                r["implementer_seat"] = implementer

    elif ev == "pull_request" and action == "closed":
        _remove_unaccepted(doc, claim.repo, "MRB", claim.id)
        _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"UAT", "PR"})
        if claim.merged:
            # FR #2375: move any accepted MRB for this PR into done (lost webhook race /
            # self-authored fix PR must not stay ACC and re-offer after merge).
            kept_acc: list[dict] = []
            done = doc.setdefault("done", [])
            for row in doc.get("accepted") or []:
                if not isinstance(row, dict):
                    continue
                if (
                    str(row.get("repo") or "") == claim.repo
                    and str(row.get("task") or "").upper() == "MRB"
                    and str(row.get("id") or "") == claim.id
                ):
                    fin = dict(row)
                    fin["result"] = "MERGED"
                    fin["merged"] = True
                    fin["done_ts"] = _utc_now()
                    done.append(fin)
                    continue
                kept_acc.append(row)
            doc["accepted"] = kept_acc
            if len(done) > DONE_CAP:
                doc["done"] = done[-DONE_CAP:]
            for ref in claim.refs:
                _remove_unaccepted_tasks(doc, claim.repo, ref, {"FR", "PR", "MRB", "UAT"})
            if is_mrb_fix_pr_title(str(claim.title or claim.line or "")):
                _remove_unaccepted_tasks(doc, claim.repo, claim.id, {"UAT", "MRB", "FR", "PR"})
            changed = "updated"
        else:
            # FR #2650: closed-unmerged must move ACC MRB to done as CLOSED (not leave
            # it for _purge_dead_mrb_accepted to stamp MERGED).
            kept_acc_cu: list[dict] = []
            done_cu = doc.setdefault("done", [])
            moved_cu = False
            for row in doc.get("accepted") or []:
                if not isinstance(row, dict):
                    continue
                if (
                    str(row.get("repo") or "") == claim.repo
                    and str(row.get("task") or "").upper() == "MRB"
                    and str(row.get("id") or "") == claim.id
                ):
                    fin = dict(row)
                    fin["result"] = "CLOSED"
                    fin["merged"] = False
                    fin["done_ts"] = _utc_now()
                    done_cu.append(fin)
                    moved_cu = True
                    continue
                kept_acc_cu.append(row)
            if moved_cu:
                doc["accepted"] = kept_acc_cu
                if len(done_cu) > DONE_CAP:
                    doc["done"] = done_cu[-DONE_CAP:]
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
        changed = _append_unaccepted(doc, claim)
    return changed


def apply_queue_event(home: Path, claim: GitClaim) -> str:
    """Apply one deterministic queue transition.

    Returns added|removed|updated|duplicate|noop|error|error:queue-*.
    FR #1811: distinguish lock/read/write failures, spool on failure, skip noop rewrite,
    drain pending under the same lock.
    """
    if claim.task not in TASK_KINDS and claim.action not in ("closed", "edited"):
        return "error"
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                _spool_pending(home, claim)
                return "error:queue-read"

            dirty = False
            for pending in _pop_all_pending(home):
                ch = _apply_claim_to_doc(doc, pending)
                if ch == "error":
                    _spool_pending(home, pending)
                elif ch != "noop":
                    dirty = True

            changed = _apply_claim_to_doc(doc, claim)
            if changed == "error":
                return "error"
            if changed != "noop":
                dirty = True

            if not dirty:
                return changed
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                _spool_pending(home, claim)
                return "error:queue-write"
            # FR #2375 / #1323: ledger hold so MERGED PRs cannot re-offer if unaccepted leaks back.
            # FR #2650: also hold closed-unmerged (ACC moved to CLOSED) so harvest receipts
            # cannot bounce back onto the offer queue after FAIL-superseded close.
            if claim.event == "pull_request" and claim.action == "closed":
                with contextlib.suppress(Exception):
                    stamp_mrb_done(home, claim.repo, claim.id)
            return changed
    except TimeoutError:
        _spool_pending(home, claim)
        return "error:queue-lock-timeout"
    except OSError:
        _spool_pending(home, claim)
        return "error:queue-write"



def canonical_worker_nick(nick: str) -> str | None:
    """Always ``<machine>-<pid>`` for legacy ``w-<short>-<pid>`` or real seat nicks (#39 gap 1).

    Must NOT return the short ``w-io-<pid>`` form: ledger ``giveup`` keys and row
    ``giveup_seats`` store ``<machine>-<pid>``. Returning the short form made
    ``w-io-*`` / ``w-mh-*`` !bored seats bypass GIVEUP / needs_human / ledger
    blocks and re-offer needs-mrb1 FRs forever while full-form seats got empty.
    """
    seat = bobreport.parse_seat_nick(nick)
    if seat:
        return f"{seat[0]}-{seat[1]}"
    legacy = bobreport.parse_worker_nick(nick)
    if legacy:
        return f"{legacy[0]}-{legacy[1]}"
    # Fallback when machine is not yet in seat_machine_ids() (cold digest / tests):
    # still accept already-canonical ``<machine>-<pid>`` (MRB #1278).
    n = (nick or "").strip().lower()
    if n and not n.startswith("bob-") and not n.startswith("w-"):
        m = re.match(r"^([a-z0-9][a-z0-9_.-]*)-(\d+)$", n)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return None


def giveup_seat_set(row: dict) -> set[str]:
    """Canonical lowercase seat nicks from ``row['giveup_seats']`` (comma list)."""
    out: set[str] = set()
    for raw in str(row.get("giveup_seats") or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        out.add((canonical_worker_nick(raw) or raw).strip().lower())
    return out


def nick_in_giveup_seats(row: dict, nick: str) -> bool:
    """True when ``nick`` (any form) is listed in the row's giveup_seats."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    seats = giveup_seat_set(row)
    if not seats:
        return False
    if me in seats:
        return True
    # also match raw nick if a non-canonical token was stored historically
    return (nick or "").strip().lower() in {
        x.strip().lower() for x in str(row.get("giveup_seats") or "").split(",") if x.strip()
    }


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


def _worker_list_busy_work(ent: dict, nick: str) -> str:
    """Non-empty work string when worker_list still shows offered/doing for nick."""
    n = (nick or "").strip().lower()
    if not n or not isinstance(ent, dict):
        return ""
    for row in ent.get("worker_list") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("nick") or "").strip().lower() != n:
            continue
        state = str(row.get("state") or "").strip().lower()
        work = str(row.get("work") or "").strip()
        if state in ("doing", "offered", "busy", "accepted") or work:
            return work or state
    return ""


def worker_working_on(home: Path, nick: str) -> str:
    """Digest working_on for this worker pid. Empty if the worker is absent.

    FR #1714: when ``worker_list`` is already idle but the legacy pid ``workers``
    map still has ``working_on`` / ``running``, heal the map (and machine roll)
    so ``!bored`` does not nak-busy forever after a lost DONE.
    """
    parsed = bobreport.parse_seat_nick(nick)
    if not parsed:
        return ""
    mid, pid = parsed
    doc = bobreport.load_digest(_root(home))
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    ent = machines.get(mid) if isinstance(machines.get(mid), dict) else {}
    if not isinstance(ent, dict):
        return ""
    list_busy = _worker_list_busy_work(ent, nick)
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    row = workers.get(str(pid))
    map_wo = ""
    if isinstance(row, dict):
        map_wo = str(row.get("working_on") or "").strip()
        map_state = str(row.get("state") or "").strip().lower()
        if not map_wo and map_state in ("running", "doing", "offered", "busy"):
            map_wo = map_state
    if map_wo and not list_busy:
        # Split brain: list idle, map busy → clear map (CAST IRON: do not clear when list busy).
        needle = ""
        m = _MRB_DOING_RX.search(map_wo)
        if m:
            needle = str(int(m.group(2)))
        with contextlib.suppress(Exception):
            bobreport.clear_seat_doing(
                home, nick, only_if_work_contains=needle or map_wo[:40]
            )
        return ""
    if list_busy:
        return list_busy if list_busy not in ("doing", "offered", "busy", "accepted") else map_wo
    return map_wo


def pending_path(home: Path) -> Path:
    return _root(home) / PENDING_NAME


def _claim_to_pending_dict(claim: GitClaim) -> dict:
    return {
        "repo": claim.repo,
        "task": claim.task,
        "id": claim.id,
        "event": claim.event,
        "action": claim.action,
        "line": claim.line,
        "refs": list(claim.refs or ()),
        "merged": claim.merged,
        "title": claim.title,
        "body": claim.body,
        "labels": list(claim.labels or ()),
        "state": claim.state,
    }


def _claim_from_pending_dict(d: dict) -> GitClaim | None:
    if not isinstance(d, dict):
        return None
    repo = str(d.get("repo") or "").strip()
    task = str(d.get("task") or "").strip()
    ident = str(d.get("id") or "").strip()
    if not repo or not ident:
        return None
    refs = d.get("refs") or ()
    if isinstance(refs, str):
        refs = [x for x in refs.split(",") if x]
    labels = d.get("labels") or ()
    if isinstance(labels, str):
        labels = [labels]
    merged = d.get("merged")
    if merged is not None and not isinstance(merged, bool):
        merged = None
    return GitClaim(
        repo=repo,
        task=task or "FR",
        id=ident,
        event=str(d.get("event") or ""),
        action=str(d.get("action") or ""),
        line=str(d.get("line") or ""),
        refs=tuple(str(x) for x in refs),
        merged=merged,
        title=str(d.get("title") or ""),
        body=str(d.get("body") or ""),
        labels=tuple(str(x) for x in labels),
        state=str(d.get("state") or ""),
    )


def _spool_pending(home: Path, claim: GitClaim) -> None:
    """Durable spool so lock/write failures do not drop webhook claims (FR #1811)."""
    try:
        path = pending_path(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_claim_to_pending_dict(claim), separators=(",", ":")) + "\n")
    except OSError:
        pass


def _pop_all_pending(home: Path) -> list[GitClaim]:
    path = pending_path(home)
    if not path.exists():
        return []
    out: list[GitClaim] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        path.unlink()
    except OSError:
        pass
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        c = _claim_from_pending_dict(d)
        if c is not None:
            out.append(c)
    return out


@contextmanager
def _lock(home: Path, *, timeout: float | None = None):
    # FR #1993: same-process chair+HTTP share an RLock (no 30s disk wait between threads).
    # FR #2729: ``timeout`` (seconds) bounds the wait; TimeoutError when the lock is busy.
    try:
        import jeeves_locks

        inproc = jeeves_locks.inproc_queue_lock()
    except Exception:  # noqa: BLE001
        inproc = None
    if inproc is not None:
        if timeout is None:
            with inproc:
                yield
            return
        if not inproc.acquire(timeout=max(0.0, float(timeout))):
            raise TimeoutError("git-claim lock busy")
        try:
            yield
        finally:
            inproc.release()
        return
    root = _root(home)
    root.mkdir(parents=True, exist_ok=True)
    path = root / LOCK_NAME
    deadline = time.time() + (LOCK_WAIT_S if timeout is None else max(0.0, float(timeout)))
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > max(30.0, LOCK_WAIT_S):
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
    # accepted_by: ACC ownership for stale-busy heal (#2369 / MRB #2371) and ACC CLOSED purge (#2361).
    for key in ("nick", "channel", "accepted_ts", "accepted_by", "offered_to", "offered_ts", "offered_channel",
                "offered_via",  # FR #2811: giveup-push sticky window
                "author_seat", "author_nick", "author", "implementer_seat", "mrb_author_seat", "mrb_fix_author_seat",
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
    # FR #2309: sticky no-ACK rebroadcast counter + skip list must survive reload.
    try:
        if row.get("offered_count") is not None:
            out["offered_count"] = int(row.get("offered_count") or 0)
    except (TypeError, ValueError):
        pass
    if row.get("sticky_skip_seats"):
        skips = row.get("sticky_skip_seats")
        if isinstance(skips, list):
            out["sticky_skip_seats"] = [str(x) for x in skips if str(x).strip()]
        else:
            out["sticky_skip_seats"] = [str(skips)]
    if row.get("repo_uat"):
        out["repo_uat"] = True
    if row.get("merged_prs"):
        mp = row.get("merged_prs")
        out["merged_prs"] = [str(x) for x in mp] if isinstance(mp, list) else [str(mp)]
    if row_needs_human(row):
        out["needs_human"] = True
    # FR #2939: one-shot announce when every live seat is self-UAT for repo UAT #0.
    if row.get("self_uat_escalated"):
        out["self_uat_escalated"] = True
    # FR #3400: orphan-ACK release marker (retry + prior ACK void note) must survive reload.
    if row.get("retry"):
        out["retry"] = True
    if row.get("note"):
        out["note"] = str(row.get("note"))
    return out


def is_repo_uat(row: dict) -> bool:
    """t853u / FR #818 / #821: UAT is per REPO only.

    Requires task=UAT, ``repo_uat``, id ``#0``, and a title/line that is not an
    mrb-*-fix / fix(mrb-N) PR title (poisoned leftover rows).
    """
    if _canon_task(row) != "UAT":
        return False
    if not bool(row.get("repo_uat")):
        return False
    ident = str(row.get("id") or "").strip().lstrip("#")
    if ident != "0":
        return False
    titleish = " ".join([str(row.get("line") or ""), str(row.get("title") or "")])
    if is_mrb_fix_pr_title(titleish):
        return False
    return True


def is_mrb_fix_pr_title(title: str) -> bool:
    """True for titles like ``fix(mrb-105):ΓÇª`` or ``mrb-105-fix:ΓÇª`` (bobiverse#224 / #781)."""
    return bool(_MRB_FIX_TITLE_RE.search(str(title or "")))


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
        "done": [row for row in (_coerce_row(r) for r in done if isinstance(r, dict)) if row][-DONE_CAP:],
    }


def _write_queue(path: Path, doc: dict) -> None:
    """Atomic replace with PermissionError retries (Windows AV/reader contention, FR #1811)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # prune done under lock so rewrites stay smaller
    done = doc.get("done")
    if isinstance(done, list) and len(done) > DONE_CAP:
        doc["done"] = done[-DONE_CAP:]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    last_exc: Exception | None = None
    for attempt in range(WRITE_REPLACE_RETRIES):
        try:
            os.replace(str(tmp), str(path))
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(0.05 * (attempt + 1))
        except OSError as exc:
            # Some Windows paths surface sharing violations as WinError 32/5 via OSError
            if getattr(exc, "winerror", None) in (5, 32) or isinstance(exc, PermissionError):
                last_exc = exc
                time.sleep(0.05 * (attempt + 1))
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise OSError("queue replace failed")


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


def _norm_row_id(ident: str | None) -> str:
    """Canonical ``#N`` id for queue row matching (FR #2458)."""
    s = str(ident or "").strip()
    if not s:
        return ""
    if s.startswith("#"):
        return s
    if s.isdigit():
        return f"#{s}"
    return s


def _row_drop_label(row: dict) -> str:
    """Short ``TASK repo#N`` label for resync/prune drop logs (FR #2899)."""
    task = str(row.get("task") or "?").upper() or "?"
    repo = str(row.get("repo") or "?").strip() or "?"
    ident = _norm_row_id(row.get("id")) or "#?"
    return f"{task} {repo}{ident}"


def _mrb_row_has_pull_provenance(row: dict) -> bool:
    """True when an MRB row looks like a real pull (FR #2927).

    Bare ``task=MRB`` + ``repo`` + ``#N`` queue junk (no URL / event / lesson labels)
    must stay unhealable so prune can drop it (FR #595). Harvest-lesson / webhook
    pull rows may omit ``url`` briefly — those get a synthesized ``/pull/N``.
    """
    if not isinstance(row, dict):
        return False
    if PULL_URL_RE.search(str(row.get("url") or "")):
        return True
    event = str(row.get("event") or "").strip().lower()
    if event in ("pull_request", "pull_request_target"):
        return True
    labels = {
        str(x).strip().lower()
        for x in (row.get("labels") or ())
        if str(x).strip()
    }
    if "harvest-lesson" in labels:
        return True
    title = str(row.get("title") or "").strip()
    if title.lower().startswith("lesson("):
        return True
    return False


def _heal_mrb_pull_url(row: dict, *, force: bool = False) -> bool:
    """Synthesize ``/pull/N`` URL when repo+#N are known (FR #2604 / #2899 / #2927).

    ``force=True`` is for resync paths that already know the id is an open pull.
    """
    if not isinstance(row, dict) or _canon_task(row) != "MRB":
        return False
    if PULL_URL_RE.search(str(row.get("url") or "")):
        return True
    # FR #2927: never invent a pull URL for fake/bare MRB rows (keeps FR #595 prune).
    if not force and not _mrb_row_has_pull_provenance(row):
        return False
    repo = str(row.get("repo") or "").strip()
    ident = _norm_row_id(row.get("id"))
    if not repo or not ident:
        return False
    if force and not str(row.get("event") or "").strip():
        row["event"] = "pull_request"
    row["url"] = f"https://github.com/{repo}/pull/{ident.lstrip('#')}"
    return bool(PULL_URL_RE.search(str(row.get("url") or "")))


def _same(row: dict, repo: str, task: str, ident: str) -> bool:
    return (
        str(row.get("repo") or "") == str(repo or "")
        and str(row.get("task") or "").upper() == str(task or "").upper()
        and _norm_row_id(row.get("id")) == _norm_row_id(ident)
    )


def _already(doc: dict, repo: str, task: str, ident: str) -> bool:
    return any(_same(row, repo, task, ident) for row in doc["unaccepted"]) or any(
        _same(row, repo, task, ident) for row in doc["accepted"]
    )


def enqueue_unaccepted(home: Path, claim: GitClaim) -> str:
    """Apply deterministic queue transition for this claim (FR #207 supersede table).

    FR #1811: pass through error:queue-* so BobCallback can announce specific errs;
    still maps success codes to legacy added|duplicate.
    FR #2803: after a real queue add/update, push offers to seats idle after ``nothing queued``.
    """
    if claim.task not in TASK_KINDS:
        return "error"
    result = apply_queue_event(home, claim)
    if result.startswith("error"):
        return result
    if result in ("added", "updated", "removed", "duplicate", "noop"):
        out = "added"
        if result == "added":
            out = "added"
        elif result == "duplicate":
            out = "duplicate"
        else:
            out = "added" if result in ("updated", "removed") else "duplicate"
        if out == "added" and result in ("added", "updated"):
            with contextlib.suppress(Exception):
                push_idle_offers_via_chair_outbox(home)
        return out
    return "error"


def load_unaccepted(home: Path) -> list[dict]:
    return list(load_queue(home).get("unaccepted") or [])


def load_accepted(home: Path) -> list[dict]:
    return list(load_queue(home).get("accepted") or [])


def _sort_key(row: dict) -> tuple:
    """FR #3205 fallback / claim_top key: MRB < UAT < FR, then lowest number, then repo.

    Prefer ``focus_ignore.offer_sort_key`` / ``ordered_unaccepted`` when a home is available.
    """
    import focus_ignore as _fi

    task = str(row.get("task") or "").strip().upper()
    return (
        _fi._TASK_ORDER.get(task, 3),
        _fi.row_offer_number(row),
        str(row.get("repo") or "").lower(),
        str(row.get("id") or ""),
    )


OFFER_PRECOMPUTE_FILE = "offer-precompute.json"


def offer_precompute_path(home: Path) -> Path:
    return bobreport.fleet_digest_home(Path(home)) / OFFER_PRECOMPUTE_FILE


def _offer_row_fingerprint(rows: list[dict]) -> str:
    parts = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        parts.append(
            f"{r.get('repo')}|{r.get('task')}|{str(r.get('id') or '').lstrip('#')}"
        )
    return "|".join(sorted(parts))


def rebuild_offer_precompute(home: Path, rows: list[dict] | None = None) -> list[dict]:
    """FR #3205: rebuild ordered candidate list from local queue + focus (no GitHub).

    Written under the digest home so !bored can walk a pre-validated order with
    zero live GitHub calls when the fingerprint still matches.
    """
    import focus_ignore as _fi

    src = list(rows) if rows is not None else list(load_unaccepted(home))
    ordered = _fi.sort_unaccepted_rows(home, src)
    payload = {
        "v": 1,
        "ts": _utc_now(),
        "fingerprint": _offer_row_fingerprint(src),
        "order": [
            {
                "repo": str(r.get("repo") or ""),
                "task": str(r.get("task") or ""),
                "id": str(r.get("id") or ""),
            }
            for r in ordered
            if isinstance(r, dict)
        ],
    }
    path = offer_precompute_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=0) + "\n", encoding="utf-8")
    tmp.replace(path)
    return ordered


def load_offer_precompute(home: Path) -> dict | None:
    path = offer_precompute_path(home)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def offer_precompute_fresh(home: Path, rows: list[dict] | None = None) -> bool:
    """True when on-disk precompute matches the current unaccepted fingerprint."""
    doc = load_offer_precompute(home)
    if not doc:
        return False
    src = list(rows) if rows is not None else list(load_unaccepted(home))
    return str(doc.get("fingerprint") or "") == _offer_row_fingerprint(src)


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
# FR #2811: giveup-push offers stay sticky through harvest_hold_s so a held assign is not stolen.
GIVEUP_OFFER_EXTRA_S = 90.0
# FR #2309: max same-nick rebroadcasts without ACK before clearing the pin.
OFFER_STICKY_MAX = 3


def offer_timeout_s(row: dict | None) -> float:
    """Sticky offer window; giveup-pushed rows get OFFER_TIMEOUT_S + GIVEUP_OFFER_EXTRA_S (FR #2811)."""
    base = float(OFFER_TIMEOUT_S)
    if isinstance(row, dict) and str(row.get("offered_via") or "").strip().lower() == "giveup":
        return base + float(GIVEUP_OFFER_EXTRA_S)
    return base


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
    ``pr_id`` / ``pr`` ΓÇö never from the bare row/issue id alone.
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


def mrb_ledger_done_hold(home: Path, repo: str, ident: str) -> bool:
    """FR #1323: True when ledger ``mrb_done`` still holds this MRB row_key."""
    try:
        led = ledger_load(home)
    except OSError:
        return False
    done_ts = _parse_iso_ts(str((led.get("mrb_done") or {}).get(_lkey(repo, ident)) or ""))
    return done_ts is not None and (time.time() - done_ts) < MRB_DONE_HOLD_S


def stamp_mrb_done(home: Path, repo: str, ident: str) -> None:
    """Record DONE MRB so re-offers stay blocked after ``done[]`` trim (FR #1323)."""

    def _upd(doc: dict) -> None:
        doc.setdefault("mrb_done", {})[_lkey(repo, ident)] = _utc_now()

    try:
        _ledger_update(home, _upd)
    except OSError:
        pass


def clear_mrb_done(home: Path, repo: str, ident: str) -> None:
    """Drop a stale ``mrb_done`` stamp (FR #1585: premature DONE while PR still open)."""

    def _upd(doc: dict) -> None:
        md = doc.get("mrb_done")
        if isinstance(md, dict):
            md.pop(_lkey(repo, ident), None)

    try:
        _ledger_update(home, _upd)
    except OSError:
        pass


def mrb_already_done(
    doc: dict, row: dict, *, home: Path | None = None, pr_exists=None
) -> bool:
    """FR #740 / #1323: True when ``done`` or ledger ``mrb_done`` covers this MRB.

    After DONE PASS/FAIL the row must not be re-offered (even if a duplicate
    lingered in ``unaccepted``, ``done[]`` rotated, or GitHub still returns HTTP 200).

    FR #1585: when ``pr_exists`` confirms the pull is still **open**, a premature
    DONE / ledger stamp must not block or purge — GitHub open wins over the stamp.
    """
    if _canon_task(row) != "MRB":
        return False
    repo = str(row.get("repo") or "").strip()
    ident = str(row.get("id") or "").strip()
    if not repo or not ident:
        return False
    want = ident if ident.startswith("#") else f"#{ident.lstrip('#')}"
    if pr_exists is not None:
        try:
            if bool(pr_exists(repo, want.lstrip("#"))):
                return False
        except Exception:
            pass
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
    if home is not None and mrb_ledger_done_hold(home, repo, want):
        return True
    return False


def mrb_row_should_survive_resync(
    row: dict,
    *,
    want: set,
    fetched: set,
) -> bool:
    """FR #1323: MERGED/closed MRB must drop even when ``offered_to`` is set.

    Previously resync kept MRB rows with ``offered_to`` that were no longer in the
    open-pull want set — those phantoms got re-offered after DONE PASS.
    """
    if not isinstance(row, dict):
        return False
    repo = str(row.get("repo") or "")
    task = str(row.get("task") or "").upper()
    ident = _norm_row_id(row.get("id"))
    if repo not in fetched:
        return True
    if task not in ("FR", "MRB"):
        return True
    if (repo, task, ident) in want:
        return True
    # FR/MRB not open on GitHub anymore — never keep (offered_to does not save it).
    return False


def mrb_row_offerable(
    row: dict,
    *,
    pr_exists=None,
) -> bool:
    """True when an MRB row has a resolvable pull URL (and optional live PR check).

    FR #595 / #247: never offer MRB without a real ``/pull/N`` (or explicit pr_id).
    FR #740 / #738: ``pr_exists`` must mean the pull is still **open** (merged/closed -> False).
    FR #2375: ``fix(mrb-N)`` / ``mrb-N-fix`` titles are never MRB targets (enqueue already
    skips them; reject at offer too if a row leaked in).
    """
    if _canon_task(row) != "MRB":
        return True
    if row.get("merged") in (True, "true", "1", 1):
        return False
    titleish = " ".join([str(row.get("title") or ""), str(row.get("line") or "")])
    if is_mrb_fix_pr_title(titleish):
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
    except GitHubLookupUnknown:
        # FR #3188 / MRB #3207: unknown (rate limit, 5xx, !bored budget) is not "gone".
        # The structural same-repo pull URL check above already passed - still offer.
        return True
    except Exception:
        # Fail closed for MRB: do not offer a possibly-fake pull URL.
        return False


# FR #846 / #838: conventional-commit Fixes PR titles are never FR issues.
_PR_SHAPED_FR_TITLE_RE = re.compile(
    r"(?i)^(fix|docs|chore|feat|refactor|test|build|ci|perf|style)(?:\([^)]*\))?:",
)


def fr_row_offerable(row: dict, *, pr_exists=None, is_pull=None, issue_open=None) -> bool:
    """True when an FR row may be offered (FR #846 / #1313 / #2340).

    Rejects FR rows that are actually pull requests:
    * URL is ``/pull/N``
    * event is ``pull_request``
    * title looks like a conventional Fixes/docs PR
    * optional ``is_pull(repo, num)`` is true for **any** PR state (open/merged/closed)
      - covers ``/issues/N`` URLs that still resolve to a PR page (#833 / #1313)
    * ``pr_exists`` kept as a deprecated alias for ``is_pull`` (do **not** pass the
      open-only ``github_pr_exists_checker`` here - MERGED PRs would stay offerable)

    FR #2340: also rejects when the issue is CLOSED:
    * row ``state`` is ``closed`` (stamped on enqueue)
    * optional ``issue_open(repo, num)`` returns False (live GitHub open-state check)

    Non-FR rows return True.
    """
    if _canon_task(row) != "FR":
        return True
    if str(row.get("event") or "").strip().lower() == "pull_request":
        return False
    raw = str(row.get("url") or "").strip()
    if PULL_URL_RE.search(raw):
        return False
    title = str(row.get("title") or "").strip() or str(row.get("line") or "").strip()
    if _PR_SHAPED_FR_TITLE_RE.match(title):
        return False
    if str(row.get("state") or "").strip().lower() == "closed":
        return False
    checker = is_pull if is_pull is not None else pr_exists
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    if checker is not None and repo and num:
        try:
            if bool(checker(repo, num)):
                return False
        except Exception:
            pass
    if issue_open is not None and repo and num:
        try:
            if not bool(issue_open(repo, num)):
                return False
        except Exception:
            pass
    return True


# FR #2729: process-wide pr_exists verdict cache for the GET /bob/v1/report purge.
PR_EXISTS_CACHE_TTL_S = 60.0
_CACHE_MISS = object()


class TTLCache:
    """Thread-safe dict-like store whose entries expire after ``ttl_s`` seconds (FR #2729).

    Supports ``get`` / ``in`` / ``[]`` like the plain dict callers already pass as
    ``cache=``; its own small mutex is never the queue lock.
    """

    def __init__(self, ttl_s: float = PR_EXISTS_CACHE_TTL_S, *, clock=time.monotonic) -> None:
        self.ttl_s = float(ttl_s)
        self._clock = clock
        self._data: dict = {}
        self._mu = threading.Lock()

    def get(self, key, default=None):
        with self._mu:
            ent = self._data.get(key)
            if ent is None:
                return default
            if self._clock() - ent[0] > self.ttl_s:
                self._data.pop(key, None)
                return default
            return ent[1]

    def __contains__(self, key) -> bool:
        return self.get(key, _CACHE_MISS) is not _CACHE_MISS

    def __getitem__(self, key):
        val = self.get(key, _CACHE_MISS)
        if val is _CACHE_MISS:
            raise KeyError(key)
        return val

    def __setitem__(self, key, value) -> None:
        with self._mu:
            self._data[key] = (self._clock(), value)

    def clear(self) -> None:
        with self._mu:
            self._data.clear()

    def __len__(self) -> int:
        with self._mu:
            return len(self._data)


PR_EXISTS_SHARED_CACHE = TTLCache(PR_EXISTS_CACHE_TTL_S)
# FR #3188: shared TTL across !bored so two seats do not re-GET the same rows every cycle.
ISSUE_OPEN_SHARED_CACHE = TTLCache(PR_EXISTS_CACHE_TTL_S)
IS_PULL_SHARED_CACHE = TTLCache(PR_EXISTS_CACHE_TTL_S)

# FR #3188: at most one live GitHub lookup while picking the next !bored offer.
# FR #3212: !bored is local-state only — zero live GitHub calls on the IRC offer path.
BORED_GITHUB_CALL_BUDGET = 0


class GitHubLookupUnknown(Exception):
    """GitHub state is unknown (non-404 error, timeout, budget). Never treat as closed."""


def _log_github_lookup_failure(
    kind: str,
    repo: str,
    num: str,
    *,
    code: int | None = None,
    rate_remaining: str | None = None,
    exc: BaseException | None = None,
    log=None,
) -> None:
    """Log lookup failure without token (FR #3188 / #3158 item 2)."""
    bits = [f"WARN git-claim {kind} unknown {repo}#{num}"]
    if code is not None:
        bits.append(f"http={code}")
    if rate_remaining is not None and str(rate_remaining).strip() != "":
        bits.append(f"rate_remaining={rate_remaining}")
    if exc is not None:
        bits.append(type(exc).__name__)
    msg = " ".join(bits)
    if log is not None:
        try:
            log(msg)
            return
        except Exception:
            pass
    print(msg, flush=True)


def _rate_remaining_from_headers(hdrs) -> str | None:
    if hdrs is None:
        return None
    try:
        get = getattr(hdrs, "get", None)
        if callable(get):
            return get("X-RateLimit-Remaining") or get("x-ratelimit-remaining")
    except Exception:
        return None
    return None


def _cache_peek(store, key):
    """Cache-only lookup for a checker store (TTLCache or plain dict); never network."""
    try:
        if hasattr(store, "get"):
            return store.get(key, _CACHE_MISS)
        return store[key] if key in store else _CACHE_MISS
    except Exception:
        return _CACHE_MISS


def _budgeted_github(fn, budget: "_GithubCallBudget", kind: str | None = None):
    """Wrap a checker so only real GitHub calls consume the shared !bored budget (FR #3188).

    Fix for MRB #3207 FAIL: cache hits (checker ``peek``) are free, and repeat calls for the
    same row in one pass share one verdict, so ``mrb_already_done`` + ``mrb_row_offerable``
    cost one lookup, not two. Any checker failure surfaces as ``GitHubLookupUnknown``.
    """
    if fn is None:
        return None
    label = kind or getattr(fn, "__name__", "check")

    def _check(repo: str, num: str):
        return budget.call(fn, repo, num, kind=label)

    _check.budget = budget
    return _check


class _GithubCallBudget:
    """Shared network-call counter for one offer_focus_top / offer_top pass (FR #3188)."""

    def __init__(self, limit: int = BORED_GITHUB_CALL_BUDGET) -> None:
        self.limit = int(limit)
        self.used = 0  # real (network) checker calls only
        self._memo: dict = {}

    def call(self, fn, repo: str, num: str, *, kind: str = "check"):
        key = (kind, id(fn), str(repo or "").strip().lower(), str(num or "").strip().lstrip("#"))
        if key in self._memo:
            ok, val = self._memo[key]
            if ok:
                return val
            raise val
        peek = getattr(fn, "peek", None)
        if callable(peek):
            try:
                hit = peek(repo, num)
            except Exception:
                hit = _CACHE_MISS
            if hit is not _CACHE_MISS:
                self._memo[key] = (True, hit)
                return hit
        if self.used >= self.limit:
            raise GitHubLookupUnknown(
                f"bored github call budget exhausted ({self.limit})"
            )
        self.used += 1
        try:
            val = fn(repo, num)
        except GitHubLookupUnknown as e:
            self._memo[key] = (False, e)
            raise
        except Exception as e:
            err = GitHubLookupUnknown(f"{kind} {repo}#{num} {type(e).__name__}")
            err.__cause__ = e
            self._memo[key] = (False, err)
            raise err from e
        self._memo[key] = (True, val)
        return val


def _live_verdict(check, row: dict) -> bool | None:
    """True/False from a (budgeted) checker for this row; None when unknown (FR #3188)."""
    if check is None:
        return None
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    if not repo or not num:
        return None
    try:
        return bool(check(repo, num))
    except Exception:
        return None


def _drop_unaccepted_row(doc: dict, row: dict, *, kind: str, reason: str, log=None) -> int:
    """Remove one definitively-dead unaccepted row and log why (FR #3188 / MRB #3207)."""
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    task = _canon_task(row)
    before = len(doc.get("unaccepted") or [])
    doc["unaccepted"] = [
        r
        for r in (doc.get("unaccepted") or [])
        if not (
            isinstance(r, dict)
            and str(r.get("repo") or "").strip() == repo
            and str(r.get("id") or "").strip().lstrip("#") == num
            and _canon_task(r) == task
        )
    ]
    dropped = before - len(doc["unaccepted"])
    if dropped:
        _log_queue_purge(f"INFO git-claim purge {kind} {repo}#{num} reason={reason}", log=log)
    return dropped


def github_pr_exists_checker(
    *,
    home: Path | None = None,
    cache: dict | None = None,
):
    """Return ``pr_exists(repo, num)`` -> True only for an **open** pull (FR #595 / #740).

    Merged or closed PRs still return HTTP 200 from GitHub; those must be False so
    seats are not re-offered MRB after DONE PASS/FAIL. Returns None when offline /
    no token (structural URL checks in ``mrb_row_offerable`` still apply).

    FR #3188: HTTP 404/410 -> False (gone). Any other failure raises
    ``GitHubLookupUnknown`` (never False) so purge paths cannot wipe the queue.
    """
    try:
        import gh_filer
    except Exception:
        return None
    # Prefer digest-home token when present (chair / LocalSystem); do not leak env (FR #2540).
    with _scoped_digest_home(home):
        src = gh_filer.ensure_gh_token_env()
    if src == "none":
        return None
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return None
    store: dict = cache if cache is not None else PR_EXISTS_SHARED_CACHE

    def _check(repo: str, num: str) -> bool:
        key = f"{repo}#{num}"
        hit = store.get(key, _CACHE_MISS)  # FR #2729: one lookup (TTL entry may expire between two)
        if hit is not _CACHE_MISS:
            return hit
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
                    store[key] = ok
                    return ok
                raise GitHubLookupUnknown(
                    f"pr_exists {repo}#{num} http={getattr(resp, 'status', '?')}"
                )
        except urllib.error.HTTPError as e:
            code = int(getattr(e, "code", 0) or 0)
            if code in (404, 410):
                store[key] = False
                return False
            _log_github_lookup_failure(
                "pr_exists",
                repo,
                num,
                code=code,
                rate_remaining=_rate_remaining_from_headers(getattr(e, "headers", None)),
                exc=e,
            )
            raise GitHubLookupUnknown(f"pr_exists {repo}#{num} http={code}") from e
        except GitHubLookupUnknown:
            raise
        except Exception as e:
            _log_github_lookup_failure("pr_exists", repo, num, exc=e)
            raise GitHubLookupUnknown(f"pr_exists {repo}#{num} {type(e).__name__}") from e

    _check.peek = lambda repo, num: _cache_peek(store, f"{repo}#{num}")
    return _check


def github_is_pull_checker(
    *,
    home: Path | None = None,
    cache: dict | None = None,
):
    """Return ``is_pull(repo, num)`` -> True when the number is a pull in **any** state (FR #1313).

    Unlike ``github_pr_exists_checker`` (open-only for MRB), MERGED/CLOSED pulls still
    return True so they are never offered as FR. Returns None when offline / no token.

    FR #3188: 404/410 -> False. Other failures raise ``GitHubLookupUnknown``.
    """
    try:
        import gh_filer
    except Exception:
        return None
    with _scoped_digest_home(home):
        src = gh_filer.ensure_gh_token_env()
    if src == "none":
        return None
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return None
    store: dict = cache if cache is not None else IS_PULL_SHARED_CACHE

    def _check(repo: str, num: str) -> bool:
        key = f"is_pull:{repo}#{num}"
        hit = store.get(key, _CACHE_MISS) if hasattr(store, "get") else (
            store[key] if key in store else _CACHE_MISS
        )
        if hit is not _CACHE_MISS:
            return hit
        if key in store and not hasattr(store, "get"):
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
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                ok = 200 <= int(getattr(resp, "status", 200) or 200) < 300
                store[key] = ok
                return ok
        except urllib.error.HTTPError as e:
            code = int(getattr(e, "code", 0) or 0)
            if code in (404, 410):
                store[key] = False
                return False
            _log_github_lookup_failure(
                "is_pull",
                repo,
                num,
                code=code,
                rate_remaining=_rate_remaining_from_headers(getattr(e, "headers", None)),
                exc=e,
            )
            raise GitHubLookupUnknown(f"is_pull {repo}#{num} http={code}") from e
        except GitHubLookupUnknown:
            raise
        except Exception as e:
            _log_github_lookup_failure("is_pull", repo, num, exc=e)
            raise GitHubLookupUnknown(f"is_pull {repo}#{num} {type(e).__name__}") from e

    _check.peek = lambda repo, num: _cache_peek(store, f"is_pull:{repo}#{num}")
    return _check


def github_issue_open_checker(
    *,
    home: Path | None = None,
    cache: dict | None = None,
):
    """Return ``issue_open(repo, num)`` -> True only for an **open** issue (FR #2340).

    Closed issues and 404/410 return False so seats are not offered dead FR work.
    Pull-request numbers that still appear under ``/issues/N`` also return False
    when ``state`` is not open (``is_pull`` remains the primary PR gate). Returns
    None when offline / no token (structural / stamped-state checks still apply).

    FR #3188: non-404 failures raise ``GitHubLookupUnknown`` — never False — so a
    rate-limit / 5xx / timeout cannot purge the whole unaccepted queue.
    """
    try:
        import gh_filer
    except Exception:
        return None
    with _scoped_digest_home(home):
        src = gh_filer.ensure_gh_token_env()
    if src == "none":
        return None
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return None
    store: dict = cache if cache is not None else ISSUE_OPEN_SHARED_CACHE

    def _check(repo: str, num: str) -> bool:
        key = f"issue_open:{repo}#{num}"
        if hasattr(store, "get"):
            hit = store.get(key, _CACHE_MISS)
            if hit is not _CACHE_MISS:
                return hit
        elif key in store:
            return store[key]
        api = f"https://api.github.com/repos/{repo}/issues/{num}"
        req = urllib.request.Request(
            api,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "bobiverse-gitclaim",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if 200 <= int(getattr(resp, "status", 200) or 200) < 300:
                    raw = resp.read()
                    try:
                        body = json.loads(
                            raw.decode("utf-8")
                            if isinstance(raw, (bytes, bytearray))
                            else raw
                        )
                    except (TypeError, ValueError, UnicodeDecodeError):
                        body = {}
                    ok = str((body or {}).get("state") or "").lower() == "open"
                    store[key] = ok
                    return ok
                raise GitHubLookupUnknown(
                    f"issue_open {repo}#{num} http={getattr(resp, 'status', '?')}"
                )
        except urllib.error.HTTPError as e:
            code = int(getattr(e, "code", 0) or 0)
            if code in (404, 410):
                store[key] = False
                return False
            _log_github_lookup_failure(
                "issue_open",
                repo,
                num,
                code=code,
                rate_remaining=_rate_remaining_from_headers(getattr(e, "headers", None)),
                exc=e,
            )
            raise GitHubLookupUnknown(f"issue_open {repo}#{num} http={code}") from e
        except GitHubLookupUnknown:
            raise
        except Exception as e:
            _log_github_lookup_failure("issue_open", repo, num, exc=e)
            raise GitHubLookupUnknown(f"issue_open {repo}#{num} {type(e).__name__}") from e

    _check.peek = lambda repo, num: _cache_peek(store, f"issue_open:{repo}#{num}")
    return _check


def _purge_fr_that_are_pulls(doc: dict, *, is_pull=None, issue_open=None) -> int:
    """Drop unaccepted FR rows whose id is a GitHub pull (any state) - FR #1313 / #2340."""
    before = len(doc.get("unaccepted") or [])
    kept: list[dict] = []
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        if _canon_task(row) == "FR" and not fr_row_offerable(
            row, is_pull=is_pull, issue_open=issue_open
        ):
            continue
        kept.append(row)
    doc["unaccepted"] = kept
    return before - len(kept)


def _fr_issue_is_closed(row: dict, *, issue_open=None) -> bool:
    """True when an FR row's GitHub issue is CLOSED (stamped and/or live check)."""
    if _canon_task(row) != "FR":
        return False
    if str(row.get("state") or "").strip().lower() == "closed":
        return True
    if issue_open is None:
        return False
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    if not repo or not num:
        return False
    try:
        return not bool(issue_open(repo, num))
    except Exception:
        return False


def _log_queue_purge(msg: str, *, log=None) -> None:
    """Log a queue purge with reason (FR #3188 / FR #2899 parity)."""
    line = str(msg)
    if log is not None:
        try:
            log(line)
            return
        except Exception:
            pass
    print(line, flush=True)


def _purge_closed_fr_unaccepted(doc: dict, *, issue_open=None, log=None) -> int:
    """Drop unaccepted FR rows whose GitHub issue is CLOSED (FR #2340).

    Mirrors ``_purge_dead_mrb_unaccepted`` for FR: stamped ``state=closed`` and/or
    live ``issue_open(repo, num) is False`` remove the row before offer.

    FR #3188: ``issue_open`` raising / unknown must not purge (see ``_fr_issue_is_closed``).
    Every drop is logged with a reason so a wipe cannot happen silently.
    """
    before = len(doc.get("unaccepted") or [])
    kept: list[dict] = []
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        if _fr_issue_is_closed(row, issue_open=issue_open):
            repo = str(row.get("repo") or "").strip()
            ident = str(row.get("id") or "").strip()
            stamped = str(row.get("state") or "").strip().lower() == "closed"
            why = "stamped-state=closed" if stamped else "issue_open=False"
            _log_queue_purge(
                f"INFO git-claim purge closed-fr {repo}{ident} reason={why}",
                log=log,
            )
            continue
        kept.append(row)
    doc["unaccepted"] = kept
    return before - len(kept)


def _purge_closed_fr_accepted(doc: dict, *, issue_open=None, home: Path | None = None) -> int:
    """Move accepted FR rows whose GitHub issue is CLOSED into done (FR #2361).

    Unaccepted CLOSED purge (#2348 / FR #2340) left ACC rows (e.g. #2340 on
    marchhare) stuck forever. Mirrors ``_purge_dead_mrb_accepted`` for FR.
    ``clear_seat_doing`` only when ``only_if_work_contains`` matches the id —
    never blanket-clear working seats (keep seats busy).
    """
    before = len(doc.get("accepted") or [])
    kept: list[dict] = []
    done = doc.setdefault("done", [])
    for row in doc.get("accepted") or []:
        if not isinstance(row, dict):
            continue
        if _fr_issue_is_closed(row, issue_open=issue_open):
            fin = dict(row)
            fin["result"] = "CLOSED"
            fin["done_ts"] = _utc_now()
            fin["state"] = "closed"
            done.append(fin)
            if home is not None:
                seat = str(
                    fin.get("nick")
                    or fin.get("accepted_by")
                    or fin.get("offered_to")
                    or ""
                ).strip()
                ident = str(fin.get("id") or "").lstrip("#")
                if seat and ident:
                    with contextlib.suppress(Exception):
                        bobreport.clear_seat_doing(
                            home, seat, only_if_work_contains=ident
                        )
            continue
        kept.append(row)
    doc["accepted"] = kept
    return before - len(kept)


def _purge_dead_mrb_unaccepted(
    doc: dict,
    *,
    pr_exists=None,
    home: Path | None = None,
    open_pulls: dict | None = None,
    fetched_repos: set | None = None,
) -> int:
    """Drop unaccepted MRB rows that are already done or no longer an open pull (FR #740 / #1323 / #2458).

    FR #1585: when ``pr_exists`` says the pull is still open, keep the row and clear
    a stale ledger ``mrb_done`` stamp so the next offline scan cannot re-kill it.

    FR #2458: when ``open_pulls`` + ``fetched_repos`` are provided (resync), drop MRB
    rows whose id is absent from that repo's open-pull set (merged/closed webhook miss).
    """
    before = len(doc.get("unaccepted") or [])
    kept: list[dict] = []
    fetched = {str(x) for x in (fetched_repos or ())}
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        if _canon_task(row) == "MRB":
            if mrb_already_done(doc, row, home=home, pr_exists=pr_exists):
                continue
            if not mrb_row_offerable(row, pr_exists=pr_exists):
                continue
            repo = str(row.get("repo") or "").strip()
            ident = _norm_row_id(str(row.get("id") or ""))
            if (
                open_pulls is not None
                and repo
                and repo in fetched
                and ident
                and ident not in (open_pulls.get(repo) or set())
            ):
                continue
            if home is not None and pr_exists is not None:
                if repo and ident and mrb_ledger_done_hold(home, repo, ident):
                    with contextlib.suppress(Exception):
                        if bool(pr_exists(repo, ident.lstrip("#"))):
                            clear_mrb_done(home, repo, ident)
        kept.append(row)
    doc["unaccepted"] = kept
    return before - len(kept)


# FR #2729: at most one purge at a time; concurrent report GETs skip instead of queueing.
_PURGE_INFLIGHT = threading.Lock()


def _mrb_verdict_key(repo, num) -> tuple[str, str]:
    return (str(repo or "").strip().lower(), str(num or "").strip().lstrip("#"))


def _mrb_row_verdict_key(row: dict) -> tuple[str, str]:
    return _mrb_verdict_key(row.get("repo"), row.get("id"))


def _is_mrb_row(row) -> bool:
    return isinstance(row, dict) and _canon_task(row) == "MRB"


def purge_dead_mrb_rows(
    home: Path, *, pr_exists=None, lock_timeout: float | None = None
) -> int:
    """FR #2458: drop dead unaccepted/accepted MRB rows; persist if changed.

    FR #2729: never call GitHub (``pr_exists``) while holding the queue lock.

    1. Under the lock, snapshot the queue.
    2. Outside the lock, ask ``pr_exists`` about every MRB row in the snapshot
       (judged on a scratch copy; no ledger/digest side effects).
    3. Re-lock, reload the queue and run the usual purge against those cached
       verdicts only. MRB rows that appeared after the snapshot are left alone.

    ``lock_timeout`` (seconds) bounds each lock wait; when the lock is busy the
    purge is skipped (returns 0). Only one purge runs at a time; a concurrent
    caller returns 0 at once.
    """
    if not _PURGE_INFLIGHT.acquire(blocking=False):
        return 0
    try:
        try:
            with _lock(home, timeout=lock_timeout):
                snap = copy.deepcopy(_load_queue_unlocked(home))
        except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
            return 0
        if not any(
            _is_mrb_row(r) for b in ("unaccepted", "accepted") for r in (snap.get(b) or [])
        ):
            return 0

        verdicts: dict[tuple[str, str], bool] = {}
        memo = None
        if pr_exists is not None:

            def _record(repo, num):
                key = _mrb_verdict_key(repo, num)
                if key in verdicts:
                    return verdicts[key]
                ok = bool(pr_exists(repo, num))  # network: outside the queue lock
                verdicts[key] = ok
                return ok

            scratch = copy.deepcopy(snap)
            with contextlib.suppress(Exception):
                _purge_dead_mrb_unaccepted(scratch, pr_exists=_record, home=None)
            with contextlib.suppress(Exception):
                _purge_dead_mrb_accepted(scratch, pr_exists=_record, home=None)

            def memo(repo, num):  # noqa: F811 - cached verdicts only, never network
                return verdicts.get(_mrb_verdict_key(repo, num), True)

        try:
            with _lock(home, timeout=lock_timeout):
                doc = _load_queue_unlocked(home)
                held: dict[str, list] = {}
                for b in ("unaccepted", "accepted"):
                    rows = list(doc.get(b) or [])
                    held[b] = rows
                    if memo is not None:
                        doc[b] = [
                            r
                            for r in rows
                            if not (_is_mrb_row(r) and _mrb_row_verdict_key(r) not in verdicts)
                        ]
                n = _purge_dead_mrb_unaccepted(doc, pr_exists=memo, home=home)
                n += _purge_dead_mrb_accepted(doc, pr_exists=memo, home=home)
                if memo is not None:
                    for b in ("unaccepted", "accepted"):
                        kept = {id(r) for r in doc.get(b) or []}
                        doc[b] = [
                            r
                            for r in held[b]
                            if id(r) in kept
                            or (_is_mrb_row(r) and _mrb_row_verdict_key(r) not in verdicts)
                        ]
                if n:
                    _write_queue(queue_path(home), doc)
                return n
        except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
            return 0
    finally:
        _PURGE_INFLIGHT.release()



def _mrb_is_dead(doc: dict, row: dict, *, pr_exists=None, home: Path | None = None) -> bool:
    """True when an MRB row should leave the live queues (merged/closed/already-done)."""
    if _canon_task(row) != "MRB":
        return False
    if mrb_already_done(doc, row, home=home, pr_exists=pr_exists):
        return True
    return not mrb_row_offerable(row, pr_exists=pr_exists)



_MRB_DOING_RX = re.compile(
    r"(?i)\bMRB\b(?:\s+(?:SimonBarnett/)?([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?))?\s*#\s*(\d+)"
)


def _orphan_mrb_repo_num(
    work: str, *, default_repo: str = "SimonBarnett/bobiverse"
) -> tuple[str, str] | None:
    m = _MRB_DOING_RX.search(str(work or ""))
    if not m:
        return None
    repo_part = (m.group(1) or "").strip()
    num = str(int(m.group(2)))
    if repo_part and "/" in repo_part:
        repo = repo_part
    elif repo_part:
        repo = f"SimonBarnett/{repo_part}"
    else:
        repo = default_repo
    return repo, num


def clear_orphan_digest_mrb_doing(
    home: Path,
    *,
    pr_exists=None,
    default_repo: str = "SimonBarnett/bobiverse",
) -> int:
    """Idle seats whose digest still says doing MRB #N after the PR is dead (FR #1508).

    FR #1430 clears doing when an *accepted* MERGED row is purged. When the ACC
    row is already gone (DONE lost / webhook race), seats stay nak-busy forever.
    Call from !bored / offer paths with the live `pr_exists` checker.

    FR #1714: also scan pid-keyed ``workers`` map (and machine ``working_on``) —
    ``worker_list`` can already be idle while the map keeps ``running`` + working_on.
    """
    if pr_exists is None or home is None:
        return 0
    import bobreport

    doc = bobreport.load_digest(home)
    machines = doc.get("machines") if isinstance(doc, dict) else None
    if not isinstance(machines, dict):
        return 0
    cleared = 0
    seen_nicks: set[str] = set()

    def _try_clear(nick: str, num: str, repo: str) -> None:
        nonlocal cleared
        n = (nick or "").strip()
        if not n or n.lower() in seen_nicks:
            return
        try:
            still_open = bool(pr_exists(repo, num))
        except Exception:
            return
        if still_open:
            return
        with contextlib.suppress(Exception):
            out = bobreport.clear_seat_doing(home, n, only_if_work_contains=num)
            if getattr(out, "ok", False):
                cleared += 1
                seen_nicks.add(n.lower())

    for mid, ent in list(machines.items()):
        if not isinstance(ent, dict):
            continue
        rows = list(ent.get("worker_list") or [])
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("state") or "").lower() != "doing":
                continue
            parsed = _orphan_mrb_repo_num(str(row.get("work") or ""), default_repo=default_repo)
            if not parsed:
                continue
            repo, num = parsed
            _try_clear(str(row.get("nick") or "").strip(), num, repo)
        # FR #1714: workers map + machine-level working_on even when list is idle.
        workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
        for pid_s, w in list(workers.items()):
            if not isinstance(w, dict):
                continue
            wo = str(w.get("working_on") or "").strip()
            if not wo:
                continue
            parsed = _orphan_mrb_repo_num(wo, default_repo=default_repo)
            if not parsed:
                continue
            repo, num = parsed
            nick = str(w.get("nick") or "").strip()
            if not nick:
                nick = f"{mid}-{pid_s}"
            _try_clear(nick, num, repo)
        mach_wo = str(ent.get("working_on") or "").strip()
        if mach_wo:
            parsed = _orphan_mrb_repo_num(mach_wo, default_repo=default_repo)
            if parsed:
                repo, num = parsed
                # Prefer a concrete seat nick from workers/list still holding that PR.
                nick = ""
                for row in rows:
                    if isinstance(row, dict) and num in str(row.get("work") or ""):
                        nick = str(row.get("nick") or "").strip()
                        if nick:
                            break
                if not nick:
                    for pid_s, w in list(workers.items()):
                        if isinstance(w, dict) and num in str(w.get("working_on") or ""):
                            nick = str(w.get("nick") or f"{mid}-{pid_s}").strip()
                            if nick:
                                break
                if nick:
                    _try_clear(nick, num, repo)
    return cleared


def _purge_dead_mrb_accepted(
    doc: dict,
    *,
    pr_exists=None,
    pr_merged=None,
    home: Path | None = None,
) -> int:
    """Move accepted MRB rows whose PR is already merged/closed into done.

    Without this, seats stay ``doing`` on MERGED PRs (#1171/#1236 class) and
    never !bored for new work — looks like an empty offer queue to monitors.

    FR #2650: when ``pr_merged`` says the pull was not merged (closed unmerged),
    stamp ``result=CLOSED`` instead of ``MERGED`` so queue.json matches GitHub.
    When ``pr_merged`` is omitted, keep the historical MERGED stamp for dead rows
    (open-only ``pr_exists`` cannot distinguish merged vs closed-unmerged).
    """
    before = len(doc.get("accepted") or [])
    kept: list[dict] = []
    done = doc.setdefault("done", [])
    for row in doc.get("accepted") or []:
        if not isinstance(row, dict):
            continue
        if _mrb_is_dead(doc, row, pr_exists=pr_exists, home=home):
            fin = dict(row)
            repo = str(fin.get("repo") or "").strip()
            num = str(fin.get("id") or "").strip().lstrip("#")
            merged_known = None
            if pr_merged is not None and repo and num:
                try:
                    merged_known = bool(pr_merged(repo, num))
                except Exception:
                    merged_known = None
            if merged_known is False:
                fin["result"] = "CLOSED"
                fin["merged"] = False
            else:
                fin["result"] = "MERGED"
                if merged_known is True:
                    fin["merged"] = True
            fin["done_ts"] = _utc_now()
            done.append(fin)
            if home is not None:
                stamp_mrb_done(home, str(fin.get("repo") or ""), str(fin.get("id") or ""))
                # FR #1430: ACC purge must idle the seat in digest or !bored stays nak busy.
                seat = str(
                    fin.get("nick")
                    or fin.get("accepted_by")
                    or fin.get("offered_to")
                    or ""
                ).strip()
                ident = str(fin.get("id") or "").lstrip("#")
                if seat:
                    with contextlib.suppress(Exception):
                        bobreport.clear_seat_doing(
                            home, seat, only_if_work_contains=ident or "MRB"
                        )
            continue
        kept.append(row)
    doc["accepted"] = kept
    return before - len(kept)


def format_assign_line(nick: str, row: dict) -> str:
    """Wire line the seats and Watch-AgentHealth parse: ``<nick>: FR|MRB|UAT owner/repo#N url``."""
    num = str(row.get("id") or "").strip().lstrip("#")
    line = f"{nick}: {_canon_task(row)} {row.get('repo') or ''}#{num} {resolve_assign_url(row)}"
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", line)).strip()


def summarize_empty_offer(home: Path, nick: str = "") -> dict:
    """Operator counts when !bored yields empty under focus (FR #1993 WP2 / FR #2309).

    Returns unaccepted / out_of_focus / require_machine / offerable estimates plus
    per-nick gate counts: self_mrb, self_uat, ledger, sticky_offered.
    ``offerable`` is rows that pass focus (when strict) and are not blocked for ``nick``
    by machine / self-MRB / self-UAT / ledger / sticky pin to another seat.
    """
    out = {
        "unaccepted": 0,
        "out_of_focus": 0,
        "require_machine": 0,
        "offerable": 0,
        "strict": False,
        "self_mrb": 0,
        "self_uat": 0,
        "ledger": 0,
        "sticky_offered": 0,
    }
    try:
        path = queue_path(home)
        raw = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
        rows = [r for r in (raw.get("unaccepted") or []) if isinstance(r, dict)]
    except Exception:
        return out
    out["unaccepted"] = len(rows)
    me = (canonical_worker_nick(nick) or nick or "").strip()
    live = live_seat_nicks(home) if me else set()
    ledger = ledger_load(home) if me else {}
    import time as _time

    now_f = _time.time()
    try:
        import focus_ignore

        strict = bool(focus_ignore.is_strict(home))
        out["strict"] = strict
        focused: set[str] = set()
        if strict:
            try:
                fdoc = focus_ignore.load_focus(home)
                focused |= {str(k) for k in (fdoc.get("repos") or {}).keys()}
                for meta in (fdoc.get("items") or {}).values():
                    if isinstance(meta, dict) and meta.get("repo"):
                        focused.add(str(meta["repo"]))
            except Exception:
                focused = set()
        offerable = 0
        out_of_focus = 0
        req_machine = 0
        self_mrb = 0
        self_uat = 0
        ledger_n = 0
        sticky_n = 0
        for r in rows:
            repo = str(r.get("repo") or "")
            if strict and focused:
                in_focus = any(
                    focus_ignore.repo_match(repo, fr) or focus_ignore.repo_match(fr, repo)
                    for fr in focused
                )
                if not in_focus:
                    out_of_focus += 1
                    continue
            row = dict(r)
            _stamp_require_machine(row)
            rm = str(row.get("require_machine") or "").strip()
            if rm and rm.lower() not in ("*", "any", "none", "-", ""):
                if not me or row_blocked_for_machine(row, me):
                    req_machine += 1
                    continue
            to = str(row.get("offered_to") or "").strip()
            sticky_pin = False
            if to:
                try:
                    age = now_f - datetime.fromisoformat(
                        str(row.get("offered_ts") or "").replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    age = 0.0
                if age < OFFER_TIMEOUT_S:
                    sticky_n += 1
                    sticky_pin = True
            if me:
                cand = enrich_uat_author_fields(raw if isinstance(raw, dict) else {}, row)
                if is_repo_uat(cand):
                    with contextlib.suppress(Exception):
                        maybe_escalate_repo_uat_all_self_uat(
                            home, cand, live=live, ledger=ledger
                        )
                if review_blocked_for_author(cand, me, live, ledger=ledger):
                    # Repo UAT exact-author / sibling stamp counts as self_uat (FR #2939);
                    # MRB exact-author stays self_mrb.
                    if is_repo_uat(cand) or _canon_task(cand) == "UAT":
                        self_uat += 1
                    else:
                        self_mrb += 1
                    continue
                why = ledger_blocks(ledger, cand, me, live)
                if why:
                    if is_repo_uat(cand) and ledger_why_is_self_uat(why):
                        self_uat += 1
                    else:
                        ledger_n += 1
                    continue
                if row_gave_up_by(cand, me) or row_needs_human(cand, me):
                    ledger_n += 1
                    continue
                skips = {
                    (canonical_worker_nick(x) or str(x)).strip().lower()
                    for x in (cand.get("sticky_skip_seats") or [])
                    if str(x).strip()
                }
                if me.lower() in skips:
                    continue
            if sticky_pin:
                to_c = (canonical_worker_nick(to) or to).strip().lower()
                me_l = me.lower()
                if me and to_c and to_c != me_l:
                    continue  # pinned to someone else
            offerable += 1
        out["out_of_focus"] = out_of_focus
        out["require_machine"] = req_machine
        out["offerable"] = offerable
        out["self_mrb"] = self_mrb
        out["self_uat"] = self_uat
        out["ledger"] = ledger_n
        out["sticky_offered"] = sticky_n
    except Exception:
        out["offerable"] = out["unaccepted"]
    return out



def clamp_empty_reply_stats(stats: dict | None) -> dict:
    """FR #2333: empty bored reply must never claim N>0 offerable for this seat.

    `summarize_empty_offer` can still count a row the live `offer_focus_top` path
    skipped (cooldown, awaits_mrb1, sticky_skip edge, PR checker, …). When the shop
    already returned empty for this nick, fold leftover offerable into `blocked_other`.
    """
    out = dict(stats or {})
    try:
        off = int(out.get("offerable") or 0)
    except (TypeError, ValueError):
        off = 0
    if off > 0:
        try:
            prev = int(out.get("blocked_other") or 0)
        except (TypeError, ValueError):
            prev = 0
        out["blocked_other"] = prev + off
        out["offerable"] = 0
    return out


def format_nothing_queued(nick: str, stats: dict | None = None) -> str:
    """Shop empty reply to a !bored seat: ONE short line, never a summary list.

    ``stats`` is accepted for backward compatibility and ignored: the focus/gate breakdown
    (FR #1993 WP2 / FR #2309 / FR #2333) goes to the chair log via ``format_empty_offer_detail``,
    not the channel. Simon: Jeeves MUST hand out work — empty reply stays short.
    """
    return f"{nick}: nothing queued"


# FR #2803: seats told "nothing queued" — push the next offerable row without waiting for !bored.
IDLE_AFTER_EMPTY_MAX_AGE_S = 900.0  # 15 minutes
IDLE_PUSH_MIN_INTERVAL_S = 5.0


def idle_after_empty_path(home: Path) -> Path:
    return _root(home) / "idle-after-empty.json"


def _load_idle_after_empty(home: Path) -> dict:
    path = idle_after_empty_path(home)
    if not path.exists():
        return {"v": 1, "seats": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {"v": 1, "seats": {}}
    if not isinstance(doc, dict):
        return {"v": 1, "seats": {}}
    seats = doc.get("seats")
    if not isinstance(seats, dict):
        seats = {}
    return {"v": 1, "seats": seats}


def _write_idle_after_empty(home: Path, doc: dict) -> None:
    path = idle_after_empty_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps({"v": 1, "seats": doc.get("seats") or {}}, indent=0, sort_keys=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(raw + "\n", encoding="utf-8")
    tmp.replace(path)


def note_idle_after_empty(
    home: Path, nick: str, channel: str, *, now: float | None = None
) -> None:
    """Record that Jeeves told this seat ``nothing queued`` (FR #2803)."""
    import time as _time

    me = (canonical_worker_nick(nick) or nick or "").strip()
    if not me:
        return
    shop = bobreport.normalize_channel(channel) if channel else (worker_shop_channel(me) or "")
    if not shop:
        return
    now_f = _time.time() if now is None else float(now)
    try:
        with _lock(home):
            doc = _load_idle_after_empty(home)
            seats = doc.setdefault("seats", {})
            prev = seats.get(me) if isinstance(seats.get(me), dict) else {}
            seats[me] = {
                "nick": me,
                "channel": shop,
                "told_at": float(now_f),
                "last_push_at": float(prev.get("last_push_at") or 0.0),
            }
            _write_idle_after_empty(home, doc)
    except (TimeoutError, OSError):
        return


def clear_idle_after_empty(home: Path, nick: str) -> None:
    """Drop an idle-after-empty entry (offered / ACK / leave / busy)."""
    me = (canonical_worker_nick(nick) or nick or "").strip()
    if not me:
        return
    me_l = me.lower()
    try:
        with _lock(home):
            doc = _load_idle_after_empty(home)
            seats = doc.get("seats") or {}
            drop = [
                k
                for k in list(seats.keys())
                if (canonical_worker_nick(k) or k).strip().lower() == me_l
            ]
            if not drop:
                return
            for k in drop:
                seats.pop(k, None)
            _write_idle_after_empty(home, doc)
    except (TimeoutError, OSError):
        return


def list_idle_after_empty(
    home: Path, *, now: float | None = None, live: set[str] | None = None
) -> list[dict]:
    """Idle seats oldest-first; prune expired and seats missing from the digest."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    live_set = set(live) if live is not None else live_seat_nicks(home)
    live_l = {
        (canonical_worker_nick(x) or x).strip().lower() for x in live_set if str(x).strip()
    }
    try:
        with _lock(home):
            doc = _load_idle_after_empty(home)
            seats = doc.get("seats") or {}
            keep: dict = {}
            rows: list[dict] = []
            for key, ent in list(seats.items()):
                if not isinstance(ent, dict):
                    continue
                nick = str(ent.get("nick") or key or "").strip()
                nick_c = (canonical_worker_nick(nick) or nick).strip()
                if not nick_c:
                    continue
                try:
                    told = float(ent.get("told_at") or 0.0)
                except (TypeError, ValueError):
                    told = 0.0
                if told <= 0 or (now_f - told) > IDLE_AFTER_EMPTY_MAX_AGE_S:
                    continue
                # If digest has any live seats, drop entries that are gone.
                if live_l and nick_c.lower() not in live_l:
                    continue
                chan = bobreport.normalize_channel(str(ent.get("channel") or "")) or (
                    worker_shop_channel(nick_c) or ""
                )
                if not chan:
                    continue
                try:
                    last_push = float(ent.get("last_push_at") or 0.0)
                except (TypeError, ValueError):
                    last_push = 0.0
                row = {
                    "nick": nick_c,
                    "channel": chan,
                    "told_at": told,
                    "last_push_at": last_push,
                }
                keep[nick_c] = row
                rows.append(row)
            if keep != seats:
                doc["seats"] = keep
                _write_idle_after_empty(home, doc)
    except (TimeoutError, OSError):
        return []
    rows.sort(key=lambda r: (float(r.get("told_at") or 0.0), str(r.get("nick") or "")))
    return rows


def offer_to_idle_seats(
    home: Path,
    *,
    say,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
    live: set[str] | None = None,
    log=None,
) -> int:
    """Push ``offer_focus_top`` to tracked idle seats (oldest first). No empty chatter (FR #2803).

    ``say(channel, text)`` delivers the assign line (IRC or chair-outbox). Returns offers sent.
    FR #2899: optional ``log(msg)`` records every successful offer (parity with bored offered).
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    idle_rows = list_idle_after_empty(home, now=now_f, live=live)
    if not idle_rows:
        return 0
    sent = 0
    for ent in idle_rows:
        nick = str(ent.get("nick") or "").strip()
        channel = str(ent.get("channel") or "").strip()
        if not nick or not channel:
            continue
        try:
            last_push = float(ent.get("last_push_at") or 0.0)
        except (TypeError, ValueError):
            last_push = 0.0
        if last_push and (now_f - last_push) < IDLE_PUSH_MIN_INTERVAL_S:
            continue
        # Busy / wrong-shop seats: do not push; clear if genuinely busy.
        if worker_working_on(home, nick):
            clear_idle_after_empty(home, nick)
            continue
        gate = bored_gate(home, nick, channel, now_f)
        if gate == "busy":
            clear_idle_after_empty(home, nick)
            continue
        if gate == "ignore":
            clear_idle_after_empty(home, nick)
            continue
        # gate == wait: recent activity throttle — skip this tick, keep idle entry.
        if gate == "wait":
            continue
        status, job = offer_focus_top(
            home,
            nick,
            channel,
            now=now_f,
            pr_exists=pr_exists,
            is_pull=is_pull,
            issue_open=issue_open,
        )
        if status == "ok" and isinstance(job, dict):
            line = format_assign_line(nick, job)
            delivered = False
            try:
                ret = say(channel, line)
                # Chair-outbox enqueue returns False on OSError/secret skip; treat as fail.
                delivered = ret is not False
            except Exception:
                delivered = False
            if not delivered:
                # Keep idle entry; stamp rate limit so we retry after IDLE_PUSH_MIN_INTERVAL_S.
                try:
                    with _lock(home):
                        doc = _load_idle_after_empty(home)
                        seats = doc.get("seats") or {}
                        cur = seats.get(nick) if isinstance(seats.get(nick), dict) else None
                        if cur is None:
                            for k, v in list(seats.items()):
                                if (canonical_worker_nick(k) or k).strip().lower() == nick.lower():
                                    cur = v if isinstance(v, dict) else None
                                    nick = k
                                    break
                        if isinstance(cur, dict):
                            cur["last_push_at"] = now_f
                            seats[nick] = cur
                            _write_idle_after_empty(home, doc)
                except (TimeoutError, OSError):
                    pass
                continue
            clear_idle_after_empty(home, nick)
            if callable(log):
                with contextlib.suppress(Exception):
                    log(f"INFO git-claim idle offered {line} nick={nick}")
            sent += 1
            continue
        # Nothing offerable for this seat: stay idle, stamp rate limit, no channel chatter.
        try:
            with _lock(home):
                doc = _load_idle_after_empty(home)
                seats = doc.get("seats") or {}
                cur = seats.get(nick) if isinstance(seats.get(nick), dict) else None
                if cur is None:
                    for k, v in list(seats.items()):
                        if (canonical_worker_nick(k) or k).strip().lower() == nick.lower():
                            cur = v if isinstance(v, dict) else None
                            nick = k
                            break
                if isinstance(cur, dict):
                    cur["last_push_at"] = now_f
                    seats[nick] = cur
                    _write_idle_after_empty(home, doc)
        except (TimeoutError, OSError):
            pass
    return sent


def push_idle_offers_via_chair_outbox(
    home: Path,
    *,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
    log=None,
) -> int:
    """Enqueue shop assign PRIVMSGs on chair-outbox for idle seats (webhook / enqueue path).

    FR #2899 / MRB #2900: when ``log`` is omitted, default to stdout ``INFO git-claim idle
    offered …`` so enqueue/webhook idle pushes match bored-offer logging without each
    caller wiring a callback.
    """

    def _say(channel: str, text: str) -> bool:
        return bool(bobreport.enqueue_chair_fleet_privmsg(home, text, channel))

    def _default_log(msg: str) -> None:
        print(str(msg), flush=True)

    return offer_to_idle_seats(
        home,
        say=_say,
        now=now,
        pr_exists=pr_exists,
        is_pull=is_pull,
        issue_open=issue_open,
        log=_default_log if log is None else log,
    )


def offer_after_giveup(
    home: Path,
    nick: str,
    channel: str,
    *,
    say,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
) -> tuple[int, dict | None]:
    """FR #2811: after GIVEUP/NACK, push the next eligible job to that seat (no empty chatter).

    Uses the same ``offer_focus_top`` gates as ``!bored``. Returns ``(1, job)`` if delivered.
    """
    status, job = offer_focus_top(
        home,
        nick,
        channel,
        now=now,
        pr_exists=pr_exists,
        is_pull=is_pull,
        issue_open=issue_open,
        offered_via="giveup",
    )
    if status != "ok" or not isinstance(job, dict):
        return 0, None
    line = format_assign_line(nick, job)
    delivered = False
    try:
        ret = say(channel, line)
        delivered = ret is not False
    except Exception:
        delivered = False
    if not delivered:
        return 0, None
    with contextlib.suppress(Exception):
        clear_idle_after_empty(home, nick)
    return 1, job


def format_empty_offer_detail(nick: str, stats: dict | None = None) -> str:
    """Operator/log line for an empty offer: focus + per-nick gate breakdown (FR #1993 WP2 / #2309 / #2333)."""
    if not stats:
        return f"{nick}: nothing queued"
    try:
        unaccepted = int(stats.get("unaccepted") or 0)
        out_of_focus = int(stats.get("out_of_focus") or 0)
        req = int(stats.get("require_machine") or 0)
        offerable = int(stats.get("offerable") or 0)
        self_mrb = int(stats.get("self_mrb") or 0)
        self_uat = int(stats.get("self_uat") or 0)
        ledger = int(stats.get("ledger") or 0)
        sticky = int(stats.get("sticky_offered") or 0)
        blocked_other = int(stats.get("blocked_other") or 0)
    except (TypeError, ValueError):
        return f"{nick}: nothing queued"
    if unaccepted <= 0:
        return f"{nick}: nothing queued"
    extra = []
    if self_mrb:
        extra.append(f"self_mrb={self_mrb}")
    if self_uat:
        extra.append(f"self_uat={self_uat}")
    if ledger:
        extra.append(f"ledger={ledger}")
    if sticky:
        extra.append(f"sticky={sticky}")
    if blocked_other:
        extra.append(f"blocked_other={blocked_other}")
    base = (
        f"{nick}: {offerable} offerable for you under focus "
        f"({unaccepted} unaccepted, {out_of_focus} out-of-focus, "
        f"{req} require_machine"
    )
    if extra:
        return base + ", " + ", ".join(extra) + ")"
    return base + ")"


def live_seat_nicks(home: Path) -> set[str]:
    """Seat nicks present in the digest for MRB/UAT author rules (FR #1401).

    Prefer canonical ``worker_list`` (tray / shop feed). Legacy pid-keyed
    ``workers`` often keeps ghost seats that never ``!bored``; counting them as
    live used to strand repo-UAT eligibility math (FR #1401). Fall back to
    ``workers`` only when ``worker_list`` is empty.
    """
    out: set[str] = set()
    try:
        doc = bobreport.load_digest(_root(home))
    except Exception:
        return out
    for mid, ent in (doc.get("machines") or {}).items():
        if not isinstance(ent, dict):
            continue
        rows = bobreport._coerce_worker_list(ent.get("worker_list"))
        if rows:
            for r in rows:
                nick = str(r.get("nick") or "").strip()
                if not nick:
                    continue
                out.add(canonical_worker_nick(nick) or nick)
            continue
        for pid in (ent.get("workers") or {}):
            if str(pid).isdigit():
                out.add(f"{mid}-{int(pid)}")
    return out



def free_seat_nicks(home: Path, live: set[str] | None = None) -> set[str]:
    """FR #2487: live seats that are idle/free (no digest working_on; not in accepted)."""
    seats = set(live) if live is not None else live_seat_nicks(home)
    busy: set[str] = set()
    try:
        doc = load_queue(home)
        for r in doc.get("accepted") or []:
            n = canonical_worker_nick(str(r.get("nick") or "")) or str(r.get("nick") or "").strip()
            if n:
                busy.add(n.lower())
    except Exception:
        pass
    out: set[str] = set()
    for n in seats:
        n_c = canonical_worker_nick(n) or (n or "").strip()
        if not n_c:
            continue
        if n_c.lower() in busy:
            continue
        if worker_working_on(home, n_c):
            continue
        out.add(n_c)
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

    for k in ("implementer_seat", "mrb_author_seat", "mrb_fix_author_seat", "author_seat", "author_nick", "author"):
        _add(str(row.get(k) or ""))
    multi = row.get("author_seats")
    if isinstance(multi, (list, tuple)):
        for item in multi:
            _add(str(item or ""))
    elif multi:
        for part in str(multi).replace(";", ",").split(","):
            _add(part)
    return found


def nick_is_row_author(row: dict, nick: str) -> bool:
    """True when ``nick`` matches any of ``row_author_seats`` (canonical seat form)."""
    authors = row_author_seats(row)
    if not authors or not (nick or "").strip():
        return False
    return nick_in_giveup_seats({"giveup_seats": ",".join(authors)}, nick)


def mrb_author_extra_from_doc(doc: dict, claim: "GitClaim") -> dict[str, str]:
    """FR #3277: author/implementer stamps for an MRB claim from queue truth.

    Used by DONE FR enqueue, PR webhook, and resync re-add so a missing
    ``author_seat`` cannot leave the PR offerable to its own implementer.
    """
    if str(getattr(claim, "task", "") or "").upper() != "MRB":
        return {}
    if getattr(claim, "harvest_lesson", False):
        opener = str(getattr(claim, "opened_by", "") or "").strip()
        if opener and bobreport.parse_seat_nick(opener):
            seat = canonical_worker_nick(opener) or opener
            return {"author_seat": seat, "implementer_seat": seat}
        return {}
    implementer = fr_implementer_seat_from_doc(doc, claim.repo, claim.refs)
    if not implementer:
        # Fall back: DONE FR that already named this pull URL.
        pull_num = str(claim.id or "").lstrip("#")
        pull_needle = f"/pull/{pull_num}"
        for row in doc.get("done") or []:
            if str(row.get("task") or "").upper() != "FR":
                continue
            url = str(row.get("url") or row.get("result") or "")
            if pull_needle not in url:
                continue
            parsed = parse_github_pull_url(url)
            if parsed and parsed[0] == claim.repo and _norm_row_id(parsed[1]) == _norm_row_id(claim.id):
                seat = str(row.get("nick") or row.get("done_by") or "").strip()
                if seat and bobreport.parse_seat_nick(seat):
                    implementer = canonical_worker_nick(seat) or seat
                    break
            if claim.repo.lower() in url.lower():
                seat = str(row.get("nick") or row.get("done_by") or "").strip()
                if seat and bobreport.parse_seat_nick(seat):
                    implementer = canonical_worker_nick(seat) or seat
                    break
    if not implementer:
        return {}
    return {"author_seat": implementer, "implementer_seat": implementer}


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



# FR #618: UAT of a PR number often lacks stamps (DONE MRB stamps the Closes issue id).
MRB_PARENT_RE = re.compile(r"(?i)\bmrb-(\d+)\b")


def _row_refs_list(row: dict) -> list[str]:
    refs = row.get("refs") or []
    if isinstance(refs, str):
        refs = [p.strip() for p in refs.replace(";", ",").split(",") if p.strip()]
    out: list[str] = []
    for r in refs:
        s = str(r).strip()
        if not s:
            continue
        if not s.startswith("#"):
            s = f"#{s}"
        out.append(s)
    return out


def related_mrb_rows(doc: dict, uat_row: dict) -> list[dict]:
    """Find MRB accepted/done rows related to a UAT row (FR #618)."""
    repo = str(uat_row.get("repo") or "")
    uid = str(uat_row.get("id") or "")
    urefs = set(_row_refs_list(uat_row))
    # fix(mrb-603) / mrb-619-nits in line/title/id
    blob = f"{uat_row.get('line') or ''}\n{uat_row.get('title') or ''}\n{uid}"
    for m in MRB_PARENT_RE.finditer(blob):
        urefs.add(f"#{m.group(1)}")
    found: list[dict] = []
    for bucket in ("accepted", "done"):
        for row in doc.get(bucket) or []:
            if str(row.get("repo") or "") != repo:
                continue
            if str(row.get("task") or "").upper() != "MRB":
                continue
            mid = str(row.get("id") or "")
            mrefs = set(_row_refs_list(row))
            if mid == uid or uid in mrefs or mid in urefs or (urefs & mrefs):
                found.append(row)
    return found


def enrich_uat_author_fields(doc: dict, row: dict) -> dict:
    """Copy UAT row with author stamps filled from related MRB rows when missing (FR #618).

    Used for repo-level UAT ``#0`` (t853u) when stamps are missing after DONE MRB
    stamped a Closes issue id or after resync dropped them. Without enrichment,
    ``review_blocked_for_author`` can miss the MRB reviewer / fix / implementer seats.
    Per-PR UAT is never offered (``is_repo_uat`` gate runs before enrich).
    """
    if _canon_task(row) != "UAT":
        return row
    out = dict(row)
    extras: dict[str, str] = {}
    for mrb in related_mrb_rows(doc, out):
        piece = uat_block_extras_from_mrb_row(
            mrb, mrb_nick=str(mrb.get("nick") or mrb.get("done_by") or "")
        )
        for k, v in piece.items():
            # First related MRB wins (accepted before done); do not let a later row clobber.
            if v and not out.get(k) and not extras.get(k):
                extras[k] = v
        # mrb-*-fix / nits author is typically the MRB reviewer; stamp explicitly when
        # this UAT targets a fix/nits PR related to that MRB.
        fix_nick = _canon_seat_nick(str(mrb.get("nick") or mrb.get("done_by") or ""))
        if fix_nick and not out.get("mrb_fix_author_seat") and not extras.get("mrb_fix_author_seat"):
            blob = f"{out.get('line') or ''}\n{out.get('title') or ''}\n{out.get('id') or ''}".lower()
            mid = str(mrb.get("id") or "").lstrip("#")
            if mid and (f"mrb-{mid}" in blob or "nits" in blob or "fix(mrb" in blob):
                extras["mrb_fix_author_seat"] = fix_nick
    out.update(extras)
    return out


def mrb_blocked_for_author(row: dict, nick: str, live: set[str], ledger: dict | None = None, *, free: set[str] | None = None) -> bool:
    """Do not hand an MRB/UAT to the author seat (or sibling on same machine) while another machine is live.

    FR #39 / #227 / #265: MRB and UAT must go to a different machine/seat than the
    FR implementer and/or MRB author when at least one other machine has a live seat.
    """
    return review_blocked_for_author(row, nick, live, ledger=ledger, free=free)


def review_blocked_for_author(
    row: dict,
    nick: str,
    live: set[str],
    ledger: dict | None = None,
    *,
    free: set[str] | None = None,
) -> bool:
    """Shared MRB+UAT author block (FR #39 / #227 / #265 / #1407 / #2604).

    Blocks when ``nick`` matches any of ``row_author_seats`` (exact seat).

    For **UAT** only: also blocks a sibling on the same machine while another machine
    has a *viable* live seat (FR #1407 / #2487). For **MRB**, self-exclusion is
    exact-seat only (FR #2604) so a same-machine sibling may review even when
    another machine looks live — two seats on one box must not strand an open PR.

    Viable other-machine seats (FR #1407): not already in ``giveup_seats``, and for
    repo-level UAT when ``ledger`` is provided, not themselves FR-implementer blocked
    (``_ledger_blocks``). Giveup / fellow-implementer seats must not strand siblings
    of the stamped author after self-UAT GIVEUP loops.

    FR #2487: when ``free`` is provided, UAT sibling viability requires the other-machine
    seat to be idle/free right now (in ``free``). When ``free`` is None, all
    ``live`` seats are treated as free (unit-test / legacy default).
    """
    task = _canon_task(row)
    if task not in ("MRB", "UAT"):
        return False
    authors = row_author_seats(row)
    if not authors:
        return False
    me = canonical_worker_nick(nick) or nick
    me_l = me.lower()
    me_p = bobreport.parse_seat_nick(me)
    me_mid = bobreport.fold_machine_id(me_p[0]) if me_p else ""
    repo_uat = is_repo_uat(row)

    def _seat_gave_up_uat(n_c: str) -> bool:
        if row_gave_up_by(row, n_c):
            return True
        if ledger is not None and repo_uat:
            other_why = _ledger_blocks(ledger, row, n_c)
            if other_why and "gave up" in other_why:
                return True
        return False

    for author in authors:
        author_l = author.lower()
        # Exact author seat: never self-MRB / self-UAT (FR #628).
        # FR #2939: do not lift exact author when others GIVEUP'd — that escape
        # disagreed with the worker self-UAT skill and stranded UAT after refuse.
        # Escalate via maybe_escalate_repo_uat_all_self_uat instead.
        if author_l == me_l:
            return True
        # FR #2604: MRB self-exclusion is exact seat only — sibling on same machine OK.
        if task == "MRB":
            continue
        author_p = bobreport.parse_seat_nick(author)
        # UAT sibling seat on the same machine: block when another machine has a viable live seat.
        if author_p and me_p:
            author_mid = bobreport.fold_machine_id(author_p[0])
            if author_mid == me_mid:
                free_set = live if free is None else free
                free_l = {
                    (canonical_worker_nick(x) or x or "").strip().lower()
                    for x in free_set
                    if str(x or "").strip()
                }
                for n in live:
                    n_c = (canonical_worker_nick(n) or n or "").strip()
                    if not n_c or _seat_gave_up_uat(n_c):
                        continue
                    p = bobreport.parse_seat_nick(n_c)
                    if not p or bobreport.fold_machine_id(p[0]) == author_mid:
                        continue
                    # FR #2339: pinned-out other-machine seats are not viable — do not
                    # strand the author-machine sibling when require_machine forbids them.
                    if row_blocked_for_machine(row, n_c):
                        continue
                    # FR #2487: busy other-machine seats are not viable for sibling block.
                    if n_c.lower() not in free_l:
                        continue
                    if ledger is not None and repo_uat:
                        other_why = _ledger_blocks(ledger, row, n_c)
                        if other_why and "implemented" in other_why:
                            continue
                    return True
    return False


def row_machine_mismatch(row: dict, nick: str) -> bool:
    """FR #628 / #732: machine pin via stamp, ``machine:<id>`` label, or title/body cues.

    Delegates to ``row_blocked_for_machine`` / ``row_require_machine`` so ``!assign``
    (``assign_row``) re-infers WP0/ionos cues the same way ``offer_focus_top`` does ΓÇö
    legacy rows that never got ``_stamp_require_machine`` must not be force-assigned
    to the wrong machine.
    """
    return row_blocked_for_machine(row, nick)


def row_gave_up_by(row: dict, nick: str) -> bool:
    return nick_in_giveup_seats(row, nick)


def offer_focus_top(
    home: Path,
    nick: str,
    channel: str,
    *,
    now: float | None = None,
    pr_exists=None,
    is_pull=None,
    issue_open=None,
    offered_via: str | None = None,
) -> tuple[str, dict | None]:
    """Focus-ordered offer for !bored (#39 gap 2). Stamps offered_to (ACK accepts it, FR #207).

    "ok" job | "empty" (nothing queued / nothing eligible under strict focus or ignore) | "error".
    A row offered to another seat within OFFER_TIMEOUT_S is skipped.
    FR #3192: a seat that still holds a live ``offered_to`` is not rebroadcast a second job
    (``bored_gate`` busy + early empty return); sticky-max clear (FR #2309) still runs so
    another seat can take a dead pin after ``OFFER_STICKY_MAX`` no-ACK attempts.
    ``pr_exists`` (optional) skips MRB rows whose pull URL 404s (FR #595 / #247).
    ``issue_open`` (optional) purges/skips FR rows whose issue is CLOSED (FR #2340).

    FR #3188: bulk purge uses stamped/structural checks only (no per-row GitHub fan-out
    on the IRC ``!bored`` path). Live checkers are budgeted to at most one call while
    picking the offered row; unknown lookups never purge.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    live = live_seat_nicks(home)
    free = free_seat_nicks(home, live)
    me_raw = (nick or "").strip()
    me = (canonical_worker_nick(me_raw) or me_raw).strip()
    ledger = ledger_load(home)
    # FR #3205: when an on-disk precompute fingerprint matches the queue, !bored uses
    # zero GitHub calls (local eligibility only). Otherwise keep the FR #3188 budget of 1.
    # Resync / webhook / explicit rebuild_offer_precompute refresh the file off the IRC path.
    try:
        with _lock(home):
            try:
                _peek = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                _peek = None
        _rows_peek = list((_peek or {}).get("unaccepted") or []) if _peek else []
    except (TimeoutError, OSError):
        _rows_peek = []
    precompute_ok = offer_precompute_fresh(home, _rows_peek)
    bored_budget = 0 if precompute_ok else BORED_GITHUB_CALL_BUDGET
    budget = _GithubCallBudget(bored_budget)
    pr_exists = _budgeted_github(pr_exists, budget, "pr_exists")
    is_pull = _budgeted_github(is_pull, budget, "is_pull")
    issue_open = _budgeted_github(issue_open, budget, "issue_open")
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            # FR #740 / #738: drop MERGED/CLOSED/already-DONE MRB before picking.
            # Also free seats stuck on accepted MERGED MRBs (#1171/#1236 class).
            # FR #3188: no live pr_exists fan-out here — stamped/ledger only.
            purged = bool(_purge_dead_mrb_unaccepted(doc, pr_exists=None, home=home))
            purged = bool(_purge_dead_mrb_accepted(doc, pr_exists=None, home=home)) or purged
            purged = bool(_purge_fr_that_are_pulls(doc)) or purged
            # FR #2340 / #3188: stamped CLOSED only at bulk; live check is budgeted in _eligible.
            purged = bool(_purge_closed_fr_unaccepted(doc)) or purged
            # FR #2361: accepted list is small (busy seats) — live check OK under the shared budget
            # unless FR #3205 precompute says zero GitHub on this !bored.
            if bored_budget > 0:
                purged = bool(
                    _purge_closed_fr_accepted(doc, issue_open=issue_open, home=home)
                ) or purged
            else:
                purged = bool(_purge_closed_fr_accepted(doc, issue_open=None, home=home)) or purged
            # FR #1508: free seats stuck doing MERGED MRB even when ACC row is gone.
            # Budgeted: at most one live call shared with the offer pick (skipped when budget 0).
            if bored_budget > 0 and pr_exists is not None:
                with contextlib.suppress(Exception):
                    if clear_orphan_digest_mrb_doing(home, pr_exists=pr_exists):
                        purged = True
            # Drop stale offered_to so a dead/non-ACKing seat cannot pin the row forever.
            # FR #2899: also clear when offered_to nick is not live (author-seat recycle).
            # FR #2927: only treat as dead-pin when the live set is non-empty. An empty
            # digest (or tests without workers) must keep one-offer-per-job sticky until
            # OFFER_TIMEOUT_S — otherwise every pin looks dead and two seats get #1.
            live_l = {
                (canonical_worker_nick(n) or n or "").strip().lower()
                for n in live
                if (canonical_worker_nick(n) or n or "").strip()
            }
            for cand in doc.get("unaccepted") or []:
                if not isinstance(cand, dict):
                    continue
                to = str(cand.get("offered_to") or "").strip()
                if not to:
                    continue
                to_c = (canonical_worker_nick(to) or to).strip().lower()
                dead_pin = bool(to_c) and bool(live_l) and to_c not in live_l
                try:
                    age = now_f - datetime.fromisoformat(
                        str(cand.get("offered_ts") or "").replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    age = offer_timeout_s(cand) + 1
                if dead_pin or age >= offer_timeout_s(cand):
                    cand.pop("offered_to", None)
                    cand.pop("offered_ts", None)
                    cand.pop("offered_channel", None)
                    cand.pop("offered_via", None)
                    purged = True

            # FR #3192: while this seat still holds a live offered_to, do not rebroadcast
            # and do not burn a second row — unless sticky max is already reached (FR #2309
            # clears the pin so another seat can take it). bored_gate already returns busy;
            # this is defense when offer_focus_top is called directly.
            me_l = me.lower()
            holding_live = False
            for cand in doc.get("unaccepted") or []:
                if not isinstance(cand, dict):
                    continue
                to = str(cand.get("offered_to") or "").strip()
                if not to:
                    continue
                them = (canonical_worker_nick(to) or to).strip().lower()
                if them != me_l:
                    continue
                try:
                    age = now_f - datetime.fromisoformat(
                        str(cand.get("offered_ts") or "").replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    age = offer_timeout_s(cand) + 1
                if age >= offer_timeout_s(cand):
                    continue
                try:
                    oc = int(cand.get("offered_count") or 0)
                except (TypeError, ValueError):
                    oc = 0
                if oc >= OFFER_STICKY_MAX:
                    # Fall through to _eligible sticky-clear path.
                    continue
                holding_live = True
                break
            if holding_live:
                if purged:
                    try:
                        _write_queue(queue_path(home), doc)
                    except OSError:
                        return "error", None
                return "empty", None

            def _same_seat(a: str, b: str) -> bool:
                ca = (canonical_worker_nick(a) or a or "").strip().lower()
                cb = (canonical_worker_nick(b) or b or "").strip().lower()
                return bool(ca) and ca == cb

            def _eligible(cand: dict) -> dict | None:
                nonlocal purged
                if row_needs_human(cand, me) or row_on_cooldown(cand, now_f, me):
                    return None  # FR #180: per-seat GIVEUP cooldown / needs-human
                if row_awaits_mrb1(cand):
                    return None  # legacy hook; row_awaits_mrb1 always False (op 2026-10-04)
                if row_skip_fr_reason(cand):
                    return None
                if repo_archived_for_queue(str(cand.get("repo") or "")):
                    return None
                if row_machine_mismatch(cand, me) or row_gave_up_by(cand, me):
                    return None
                if ledger_blocks(ledger, cand, me, live):
                    if is_repo_uat(cand):
                        with contextlib.suppress(Exception):
                            if maybe_escalate_repo_uat_all_self_uat(
                                home,
                                cand,
                                live=live,
                                ledger=ledger,
                                locked_doc=doc,
                            ):
                                purged = True
                    return None
                if str(cand.get("task") or "").upper() == "FR" and fr_is_superseded(
                    doc, str(cand.get("repo") or ""), str(cand.get("id") or "")
                ):
                    return None
                # FR #3188: one budgeted live open-check; definitive closed -> purge this row only.
                if _canon_task(cand) == "FR" and issue_open is not None:
                    repo = str(cand.get("repo") or "").strip()
                    num = str(cand.get("id") or "").strip().lstrip("#")
                    if repo and num and str(cand.get("state") or "").strip().lower() != "closed":
                        try:
                            if not bool(issue_open(repo, num)):
                                _log_queue_purge(
                                    f"INFO git-claim purge closed-fr {repo}#{num} "
                                    f"reason=issue_open=False"
                                )
                                doc["unaccepted"] = [
                                    r
                                    for r in (doc.get("unaccepted") or [])
                                    if not (
                                        isinstance(r, dict)
                                        and str(r.get("repo") or "").strip() == repo
                                        and str(r.get("id") or "").strip().lstrip("#") == num
                                        and _canon_task(r) == "FR"
                                    )
                                ]
                                purged = True
                                return None
                        except Exception:
                            pass
                # FR #1313 / MRB #3207: definitive is_pull=True on this FR row -> purge it only.
                if _canon_task(cand) == "FR" and _live_verdict(is_pull, cand) is True:
                    if _drop_unaccepted_row(doc, cand, kind="fr-is-pull", reason="is_pull=True"):
                        purged = True
                    return None
                if not fr_row_offerable(
                    cand, is_pull=is_pull, pr_exists=pr_exists, issue_open=None
                ):
                    return None
                if str(cand.get("task") or "").upper() == "UAT" and not is_repo_uat(cand):
                    return None
                # FR #740 / MRB #3207: one shared lookup per MRB row; definitive not-open
                # purges this row only; unknown (budget / 403 / 5xx) still offers.
                if _canon_task(cand) == "MRB" and _live_verdict(pr_exists, cand) is False:
                    if _drop_unaccepted_row(doc, cand, kind="dead-mrb", reason="pr_exists=False"):
                        purged = True
                    return None
                if mrb_already_done(doc, cand, home=home, pr_exists=pr_exists):
                    return None
                if not mrb_row_offerable(cand, pr_exists=pr_exists):
                    return None
                to = str(cand.get("offered_to") or "").strip()
                if to and not _same_seat(to, me):
                    try:
                        age = now_f - datetime.fromisoformat(
                            str(cand.get("offered_ts") or "").replace("Z", "+00:00")
                        ).timestamp()
                    except ValueError:
                        age = offer_timeout_s(cand) + 1
                    if age < offer_timeout_s(cand):
                        return None
                skips = {
                    (canonical_worker_nick(x) or str(x)).strip().lower()
                    for x in (cand.get("sticky_skip_seats") or [])
                    if str(x).strip()
                }
                if me.lower() in skips:
                    return None
                # FR #2309: sticky same-nick pin past OFFER_STICKY_MAX -> clear for other seats.
                if to and _same_seat(to, me):
                    try:
                        oc = int(cand.get("offered_count") or 0)
                    except (TypeError, ValueError):
                        oc = 0
                    if oc >= OFFER_STICKY_MAX:
                        cand.pop("offered_to", None)
                        cand.pop("offered_ts", None)
                        cand.pop("offered_channel", None)
                        skip_list = [
                            str(x).strip()
                            for x in (cand.get("sticky_skip_seats") or [])
                            if str(x).strip()
                        ]
                        if me not in skip_list and me.lower() not in {
                            (canonical_worker_nick(x) or x).strip().lower() for x in skip_list
                        }:
                            skip_list.append(me)
                        cand["sticky_skip_seats"] = skip_list
                        purged = True
                        return None
                cand_eff = enrich_uat_author_fields(doc, cand)
                if review_blocked_for_author(cand_eff, me, live, ledger=ledger, free=free):
                    if is_repo_uat(cand):
                        with contextlib.suppress(Exception):
                            if maybe_escalate_repo_uat_all_self_uat(
                                home,
                                cand,
                                live=live,
                                ledger=ledger,
                                locked_doc=doc,
                            ):
                                purged = True
                    return None
                # FR #1093: stamp WP0/issue pins before the machine gate (stale rows).
                _stamp_require_machine(cand_eff)
                if row_blocked_for_machine(cand_eff, me):
                    return None
                return cand_eff

            # Prefer focus order. If that yields nothing, fall back only within focused
            # repos when strict (operator asked to focus bobiverse — do not leak Club-Madeira
            # etc.). When strict is off, fall back to the full unaccepted list.
            import focus_ignore  # lazy: avoid import cycle at module load

            order = ordered_unaccepted(home, doc["unaccepted"])
            pick = None
            for cand in order:
                pick = _eligible(cand)
                if pick is not None:
                    break
            if pick is None:
                if focus_ignore.is_strict(home):
                    focused = set()
                    try:
                        fdoc = focus_ignore.load_focus(home)
                        focused |= {str(k) for k in (fdoc.get("repos") or {}).keys()}
                        for meta in (fdoc.get("items") or {}).values():
                            if isinstance(meta, dict) and meta.get("repo"):
                                focused.add(str(meta["repo"]))
                    except Exception:
                        focused = set()
                    fallback = [
                        r for r in (doc.get("unaccepted") or [])
                        if isinstance(r, dict)
                        and (
                            not focused
                            or any(
                                focus_ignore.repo_match(str(r.get("repo") or ""), fr)
                                or focus_ignore.repo_match(fr, str(r.get("repo") or ""))
                                for fr in focused
                            )
                        )
                    ]
                else:
                    fallback = [
                        r for r in (doc.get("unaccepted") or [])
                        if isinstance(r, dict)
                    ]
                # FR #3205: fallback uses the same kind+number order as focus walk.
                fallback.sort(key=lambda r: focus_ignore.offer_sort_key(home, r))
                for cand in fallback:
                    pick = _eligible(cand)
                    if pick is not None:
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
                    # FR #618: persist enriched author stamps (pick may be enrich_uat_author_fields copy).
                    job = dict(pick)
                    # Prefer live queue row fields (pick may be enrich copy without offered_*).
                    prev_to = str(row.get("offered_to") or job.get("offered_to") or "").strip()
                    prev_ts = str(row.get("offered_ts") or job.get("offered_ts") or "").strip()
                    try:
                        prev_count = int(row.get("offered_count") or job.get("offered_count") or 0)
                    except (TypeError, ValueError):
                        prev_count = 0
                    same = bool(prev_to) and _same_seat(prev_to, me)
                    job["offered_to"] = me
                    # FR #2309: rebroadcast keeps original offered_ts so OFFER_TIMEOUT can free the row.
                    if same and prev_ts:
                        job["offered_ts"] = prev_ts
                    else:
                        job["offered_ts"] = _utc_now()
                    job["offered_count"] = prev_count + 1
                    job["offered_channel"] = bobreport.normalize_channel(channel) if channel else ""
                    via = str(offered_via or "").strip()
                    if via:
                        job["offered_via"] = via
                    elif not same:
                        job.pop("offered_via", None)
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
            # FR #3205: keep precompute fingerprint in sync after stamp so the next
            # !bored can stay on the zero-GitHub path when the set of rows is unchanged.
            with contextlib.suppress(Exception):
                rebuild_offer_precompute(home, list(doc.get("unaccepted") or []))
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
    is_pull=None,
    issue_open=None,
) -> tuple[str, dict | None]:
    """Peek oldest eligible unaccepted and stamp offered_to without accepting (FR #207 / #180)."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    budget = _GithubCallBudget(BORED_GITHUB_CALL_BUDGET)
    pr_exists = _budgeted_github(pr_exists, budget, "pr_exists")
    is_pull = _budgeted_github(is_pull, budget, "is_pull")
    issue_open = _budgeted_github(issue_open, budget, "issue_open")
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            if not doc["unaccepted"]:
                return "empty", None
            # FR #3188: stamped/structural bulk purge only; live checks are budgeted below.
            purged = bool(_purge_dead_mrb_unaccepted(doc, pr_exists=None, home=home))
            purged = bool(_purge_dead_mrb_accepted(doc, pr_exists=None, home=home)) or purged
            purged = bool(_purge_fr_that_are_pulls(doc)) or purged
            purged = bool(_purge_closed_fr_unaccepted(doc)) or purged
            # Accepted list is small — live check under the shared budget (FR #2361).
            purged = bool(
                _purge_closed_fr_accepted(doc, issue_open=issue_open, home=home)
            ) or purged
            # FR #1508: free seats stuck doing MERGED MRB even when ACC row is gone.
            if pr_exists is not None:
                with contextlib.suppress(Exception):
                    if clear_orphan_digest_mrb_doing(home, pr_exists=pr_exists):
                        purged = True
            doc["unaccepted"].sort(key=_sort_key)
            pick_i = None
            i = 0
            while i < len(doc.get("unaccepted") or []):
                row = doc["unaccepted"][i]
                if row_needs_human(row, nick or "") or row_on_cooldown(row, now_f, nick or "") or row_skip_fr_reason(row):
                    i += 1
                    continue
                if row_awaits_mrb1(row):
                    i += 1
                    continue  # legacy hook; always False (op 2026-10-04)
                if repo_archived_for_queue(str(row.get("repo") or "")):
                    i += 1
                    continue  # FR #785
                if str(row.get("task") or "").upper() == "FR" and fr_is_superseded(
                    doc, str(row.get("repo") or ""), str(row.get("id") or "")
                ):
                    i += 1
                    continue  # FR #254
                if _canon_task(row) == "FR" and issue_open is not None:
                    repo = str(row.get("repo") or "").strip()
                    num = str(row.get("id") or "").strip().lstrip("#")
                    if repo and num and str(row.get("state") or "").strip().lower() != "closed":
                        try:
                            if not bool(issue_open(repo, num)):
                                _log_queue_purge(
                                    f"INFO git-claim purge closed-fr {repo}#{num} "
                                    f"reason=issue_open=False"
                                )
                                del doc["unaccepted"][i]
                                purged = True
                                continue
                        except Exception:
                            pass
                # FR #1313 / MRB #3207: definitive is_pull=True on this FR row -> purge it only.
                if _canon_task(row) == "FR" and _live_verdict(is_pull, row) is True:
                    if _drop_unaccepted_row(doc, row, kind="fr-is-pull", reason="is_pull=True"):
                        purged = True
                        continue
                    i += 1
                    continue
                if not fr_row_offerable(
                    row, is_pull=is_pull, pr_exists=pr_exists, issue_open=None
                ):
                    i += 1
                    continue  # FR #846 / #838 / #2340
                # FR #818 / t853u: never offer legacy per-PR UAT (same gate as offer_focus_top).
                if str(row.get("task") or "").upper() == "UAT" and not is_repo_uat(row):
                    i += 1
                    continue
                # FR #740 / MRB #3207: definitive not-open MRB -> purge this row only.
                if _canon_task(row) == "MRB" and _live_verdict(pr_exists, row) is False:
                    if _drop_unaccepted_row(doc, row, kind="dead-mrb", reason="pr_exists=False"):
                        purged = True
                        continue
                    i += 1
                    continue
                if mrb_already_done(doc, row, home=home, pr_exists=pr_exists):
                    i += 1
                    continue  # FR #740 / #1585
                if not mrb_row_offerable(row, pr_exists=pr_exists):
                    i += 1
                    continue
                row_eff = enrich_uat_author_fields(doc, row)
                live = live_seat_nicks(home)
                led = ledger_load(home)
                if row_blocked_for_machine(row_eff, nick or "") or review_blocked_for_author(
                    row_eff, (nick or "").strip(), live, ledger=led
                ):
                    i += 1
                    continue
                pick_i = i
                # Persist enrichment onto the queued row when we filled stamps.
                if row_eff is not row:
                    doc["unaccepted"][i] = dict(row_eff)
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


def ledger_clear_giveup(
    home: Path,
    repo: str,
    ident: str,
    nick: str | None = None,
    task: str = "FR",
) -> int:
    """FR #2446 operator heal: drop ledger giveup for ``repo#ident`` (one nick or all nicks).

    Returns how many nick entries were cleared for the row key. Does not rewrite
    linked-ref keys (operator clears the living FR/issue key that is stuck).
    """
    key = _lkey(repo, ident)
    task_u = (task or "FR").upper()
    me = _canon_ledger_nick(nick) if nick else ""
    cleared = [0]

    def _f(doc: dict) -> None:
        gu = doc.get("giveup") or {}
        if key not in gu or not isinstance(gu[key], dict):
            return
        bucket = gu[key]
        if me:
            tl = bucket.get(me) or []
            if task_u in tl:
                bucket[me] = [t for t in tl if t != task_u]
                cleared[0] += 1
                if not bucket[me]:
                    bucket.pop(me, None)
        else:
            for n, tl in list(bucket.items()):
                if task_u in (tl or []):
                    bucket[n] = [t for t in (tl or []) if t != task_u]
                    cleared[0] += 1
                    if not bucket[n]:
                        bucket.pop(n, None)
        if not bucket:
            gu.pop(key, None)

    try:
        _ledger_update(home, _f)
    except OSError:
        return 0
    return cleared[0]


def live_seats_matching_require_machine(live: set[str], required: str) -> list[str]:
    """Live seat nicks that match a ``require_machine`` pin (FR #2446)."""
    req = str(required or "").strip()
    if not req or req.lower() in ("*", "any", "none", "-", ""):
        return []
    out: list[str] = []
    for nick in sorted(live or ()):
        if seat_matches_require_machine(str(nick), req):
            out.append(str(nick))
    return out


def require_machine_all_live_gave_up(
    home: Path, row: dict, live: set[str] | None = None
) -> list[str]:
    """FR #2446: when a living require_machine row is GIVEUP'd by every live seat on that machine.

    Returns the matching live nicks (all gave up) or ``[]`` when the heal/surface
    condition does not apply (no pin, no matching live seats, or at least one
    matching seat has not given up).
    """
    if not isinstance(row, dict):
        return []
    row_eff = dict(row)
    _stamp_require_machine(row_eff)
    req = str(row_eff.get("require_machine") or "").strip()
    if not req or req.lower() in ("*", "any", "none", "-", ""):
        return []
    seats = live if live is not None else live_seat_nicks(home)
    matching = live_seats_matching_require_machine(set(seats or ()), req)
    if not matching:
        return []
    ledger = ledger_load(home)
    task = _canon_task(row_eff)
    blocked: list[str] = []
    for nick in matching:
        why = _ledger_blocks(ledger, row_eff, nick)
        if why and "gave up" in why:
            blocked.append(nick)
            continue
        if row_gave_up_by(row_eff, nick):
            blocked.append(nick)
            continue
        return []
    return blocked if len(blocked) == len(matching) else []


# FR #2486: Living / Refs-only tracking umbrellas keep operator GIVEUPs — auto-heal
# must not re-offer them after dual pin-machine GIVEUP (e.g. bobiverse#1993).
_LIVING_TRACKING_UMBRELLA_RE = re.compile(
    r"(?i)\bliving\s+fr\b|\brefs[-\s]?only\b|\bkeep\s+appending\b"
)
_LIVING_TRACKING_LABELS = frozenset(
    {"living", "living-fr", "refs-only", "refs_only", "tracking-umbrella", "tracking_umbrella"}
)


def row_skip_pin_ledger_heal_reason(row: dict) -> str | None:
    """FR #2486: why ``heal_require_machine_all_gave_up`` must leave this row alone."""
    labels = {
        str(x).strip().lower().replace("_", "-")
        for x in (row.get("labels") or [])
        if str(x or "").strip()
    }
    if labels & _LIVING_TRACKING_LABELS:
        return "living_tracking_label"
    blob = f"{row.get('title') or ''}\n{row.get('body') or ''}\n{row.get('line') or ''}"
    if _LIVING_TRACKING_UMBRELLA_RE.search(blob):
        return "living_tracking_body"
    return None


def heal_require_machine_all_gave_up(
    home: Path, live: set[str] | None = None
) -> list[str]:
    """Clear ledger giveup when every live pin-machine seat gave up a living FR (FR #2446).

    FR #2486: skips Living FR / Refs-only tracking umbrellas so operator GIVEUPs stick.

    Returns human-readable heal lines (repo#id + nick count). Shop IRC stays short;
    callers log these for operators / monitors.
    """
    try:
        path = queue_path(home)
        raw = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
        rows = [r for r in (raw.get("unaccepted") or []) if isinstance(r, dict)]
    except Exception:
        return []
    seats = live if live is not None else live_seat_nicks(home)
    healed: list[str] = []
    for row in rows:
        if row_skip_pin_ledger_heal_reason(row):
            continue
        blocked = require_machine_all_live_gave_up(home, row, seats)
        if not blocked:
            continue
        repo = str(row.get("repo") or "")
        ident = str(row.get("id") or "")
        task = _canon_task(row)
        n = 0
        for nick in blocked:
            n += ledger_clear_giveup(home, repo, ident, nick=nick, task=task)
        if n:
            healed.append(f"{repo}{ident if str(ident).startswith('#') else '#' + str(ident)} cleared={n}")
    return healed


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


def _uat_cycle_fr_touch_count(ledger: dict, row: dict, nick: str) -> int:
    """How many link keys of this repo UAT the seat holds role ``FR`` on (FR #1407)."""
    me = _canon_ledger_nick(nick)
    if not me:
        return 0
    tc = ledger.get("touch") or {}
    n = 0
    for k in _row_link_keys(row):
        roles = (tc.get(k) or {}).get(me) or []
        if "FR" in roles:
            n += 1
    return n


def ledger_why_is_self_uat(why: str) -> bool:
    """True when a ledger block reason is self-UAT (authored or MRB'd the cycle)."""
    w = (why or "").lower()
    return ("implemented" in w) or ("reviewed" in w) or ("no self-uat" in w)


def repo_uat_no_eligible_live_seat(
    ledger: dict, row: dict, live
) -> bool:
    """FR #2939: True when every live seat is giveup- or self-UAT-blocked for repo UAT."""
    if not is_repo_uat(row):
        return False
    seats = {s for s in (live or set()) if str(s or "").strip()}
    if not seats:
        return False
    for s in seats:
        if row_gave_up_by(row, s):
            continue
        why = _ledger_blocks(ledger, row, s)
        if not why:
            return False
        if "gave up" in why:
            continue
        if ledger_why_is_self_uat(why):
            continue
        # Other ledger block (e.g. FR-done hold) — still not eligible, keep scanning.
        continue
    return True


def stamp_repo_uat_self_uat_escalate(row: dict) -> bool:
    """Stamp needs_human + self_uat_escalated on a queue row (in-memory). True if newly stamped."""
    if not is_repo_uat(row):
        return False
    already = bool(row.get("self_uat_escalated"))
    row["needs_human"] = True
    row["self_uat_escalated"] = True
    return not already


def announce_repo_uat_self_uat_escalate(home: Path, repo: str) -> bool:
    """One-shot #bobiverse announce for stranded repo UAT (FR #2939)."""
    repo_s = (repo or "").strip() or "repo"
    msg = (
        f"UAT {repo_s}#0 stranded: every live seat is self-UAT "
        f"(authored or MRB'd this cycle). Needs a fresh/uninvolved seat or a human."
    )
    try:
        return bool(bobreport.enqueue_chair_fleet_privmsg(home, msg, bobreport.FLEET_CHANNEL))
    except Exception:
        return False


def maybe_escalate_repo_uat_all_self_uat(
    home: Path,
    row: dict,
    *,
    live=None,
    ledger: dict | None = None,
    locked_doc: dict | None = None,
) -> bool:
    """FR #2939: when no live seat can take repo UAT (all self-UAT / giveup), escalate once.

    Stamps ``needs_human`` + ``self_uat_escalated`` on the queue row and announces on
    #bobiverse that UAT needs a fresh/uninvolved seat or a human. Returns True when
    this call performed (or confirmed) the escalation.

    When ``locked_doc`` is provided the caller already holds the queue lock — mutate that
    doc in place and do not re-acquire (file lock is not re-entrant).
    """
    if not is_repo_uat(row):
        return False
    if row.get("self_uat_escalated") and row_needs_human(row, ""):
        return True
    led = ledger if ledger is not None else ledger_load(home)
    seats = set(live) if live is not None else live_seat_nicks(home)
    if not repo_uat_no_eligible_live_seat(led, row, seats):
        return False
    repo = str(row.get("repo") or "").strip() or "repo"
    newly = False

    def _apply(doc: dict) -> bool:
        nonlocal newly
        for r in doc.get("unaccepted") or []:
            if not isinstance(r, dict) or not is_repo_uat(r):
                continue
            if str(r.get("repo") or "").strip().lower() != repo.lower():
                continue
            newly = stamp_repo_uat_self_uat_escalate(r)
            row["needs_human"] = True
            row["self_uat_escalated"] = True
            return True
        # Row not yet in queue (unit test) — stamp the caller copy only.
        newly = stamp_repo_uat_self_uat_escalate(row)
        return newly

    try:
        if locked_doc is not None:
            _apply(locked_doc)
        else:
            with _lock(home):
                doc = _load_queue_unlocked(home)
                if _apply(doc):
                    _write_queue(queue_path(home), doc)
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return False
    if newly:
        announce_repo_uat_self_uat_escalate(home, repo)
    return True


def ledger_blocks(ledger: dict, row: dict, nick: str, live=None) -> str:
    """See ``_ledger_blocks``.

    FR #2939: repo UAT self-UAT (FR or MRB cycle touch) is never escaped. The old
    all-blocked escape (#1407 / #1416) offered a seat that then GIVEUP'd per the
    worker skill. When every live seat is self-UAT / giveup blocked, call
    ``maybe_escalate_repo_uat_all_self_uat`` (offer / empty-offer paths) instead.
    ``live`` remains in the signature for call-site compatibility.
    """
    _ = live  # retained for API compatibility / escalate callers
    return _ledger_blocks(ledger, row, nick)


def _ledger_blocks(ledger: dict, row: dict, nick: str) -> str:
    """Why this seat must not get this row ('' = ok), from the durable ledger.

    * a seat that gave up the row (or its linked PR/issue) in the same MRB/UAT/FR family never gets it again;
    * UAT: blocked for the FR implementer and the MRB reviewer of any linked issue/PR;
    * MRB: blocked for the FR implementer of any linked issue/PR.
    * repo-level UAT (FR #2939): same as UAT — FR *or* MRB cycle touch is self-UAT.
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
        if k == own and task in tl:
            return f"{nick} already gave up {k}"
        # t860u: a GIVEUP on a LINKED row only blocks the same job kind (a seat that gave up the UAT of a
        # linked issue as "self-UAT" can still review the PR); only the row's own key blocks any kind.
        if not repo_level and task in ("MRB", "UAT") and task in tl:
            return f"{nick} already gave up linked {k}"
    if task in ("MRB", "UAT"):
        # UAT (including repo-level #0): FR implementer OR MRB reviewer (FR #2939).
        # MRB rows: FR implementer only.
        bad = {"FR", "MRB"} if task == "UAT" else {"FR"}
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
    if verb_u == "DONE" and task_u == "MRB":
        # FR #1323: survive done[] trim / resync races — do not re-offer this MRB.
        stamp_mrb_done(home, repo, ident)
    # t860u: working an FR (ACK/DONE, "DONE existing PR, no duplicate", URL of a PR that already existed) is
    # NOT authorship: it is recorded as the informational role "FRW" and never blocks review. Only the PR's
    # real commit authors (``ledger_refresh_authors`` -> role "FR") and the MRB reviewer block review/UAT.
    if verb_u in ("ACK", "DONE") and task_u in ("FR", "MRB"):
        ledger_touch(home, nick, repo, "FRW" if task_u == "FR" else task_u, keys)
    if verb_u == "DONE" and task_u == "FR":
        parsed = parse_github_pull_url(url or result or "")
        if parsed:
            ledger_touch(home, nick, parsed[0], "FRW", [_lkey(parsed[0], parsed[1])])


def github_pr_seat_fetcher(*, home: Path | None = None):
    """Return ``fetch(repo, num) -> set[str] | None`` of seat nicks that authored commits on a PR.

    Seats commit as their nick (``marchhare-41928``), so the PR's commit authors are the ground truth for
    "who wrote this" - independent of queue history. ``set()`` = not a PR / no seat commits; ``None`` =
    could not tell (offline / no token / transient error; not cached)."""
    try:
        import gh_filer
    except Exception:
        return None
    with _scoped_digest_home(home):
        src = gh_filer.ensure_gh_token_env()
    if src == "none":
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


def _accepted_holder_nick(row: dict) -> str:
    """Seat that owns an accepted row (``nick`` or legacy ``accepted_by``)."""
    raw = str(row.get("nick") or row.get("accepted_by") or "").strip()
    return canonical_worker_nick(raw) or raw


def _row_to_unaccepted_retry(row: dict) -> dict:
    """FR #3400: strip accept/offer stamps and mark prior ACK void for re-offer."""
    out = dict(row)
    for key in (
        "nick",
        "channel",
        "accepted_ts",
        "accepted_by",
        "offered_to",
        "offered_ts",
        "offered_channel",
    ):
        out.pop(key, None)
    out["retry"] = True
    out["note"] = "prior ACK void"
    return out


def _release_accepted_for_nick_unlocked(doc: dict, nick: str) -> list[dict]:
    """Move accepted rows held by ``nick`` back onto ``unaccepted`` (caller holds lock)."""
    want = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not want:
        return []
    kept: list[dict] = []
    released: list[dict] = []
    for row in list(doc.get("accepted") or []):
        if not isinstance(row, dict):
            continue
        holder = _accepted_holder_nick(row).lower()
        if holder == want:
            released.append(_row_to_unaccepted_retry(row))
        else:
            kept.append(row)
    if not released:
        return []
    doc["accepted"] = kept
    doc["unaccepted"] = list(doc.get("unaccepted") or []) + released
    return released


def release_accepted_for_departed_nick(home: Path, nick: str) -> list[dict]:
    """FR #3400: seat left the shop — return its ACKed rows to unaccepted (prior ACK void).

    Local queue only; no GitHub. Live seats are never passed here (worker-remove / reconcile).
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return []
            released = _release_accepted_for_nick_unlocked(doc, nick)
            if not released:
                return []
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return []
            return released
    except (TimeoutError, OSError):
        return []


def assign_row(
    home: Path,
    nick: str,
    repo: str,
    task: str,
    ident: str,
    *,
    now: float | None = None,
    pr_exists=None, is_pull=None, issue_open=None,
) -> tuple[str, dict | str]:
    """Chair-driven manual assign (t849u): stamp ``offered_to`` on one named unaccepted row.

    Returns ("ok", job) -> caller posts ``format_assign_line`` in the worker's shop channel as Jeeves
    and the worker's ACK accepts it (``accept_offered``); or ("refused", reason).
    The same eligibility as ``offer_focus_top`` applies: real seat nick, not busy, row queued and
    unaccepted, no self-MRB/UAT, not needs-human/skip/cooldown/machine-pinned/already given up by
    this seat, not offered to another seat inside OFFER_TIMEOUT_S.

    FR #3400: refuse assign to a nick not in the shop (not a live seat). If the named job is only
    on ``accepted`` under a departed nick, release it (prior ACK void) then offer.
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
    live_l = {n.lower() for n in live}
    # FR #3400: refuse assign to a nick absent from the machine's worker_list when that
    # list is non-empty (reconcile/PART already dropped them). Empty list = unknown
    # presence (tests / cold digest) — do not block.
    seat_mid = bobreport.parse_seat_nick(me)
    if seat_mid:
        try:
            dig = bobreport.load_digest(_root(home))
            ent = (dig.get("machines") or {}).get(seat_mid[0]) or {}
            shop_rows = bobreport._coerce_worker_list(ent.get("worker_list"))
        except Exception:
            shop_rows = []
        if shop_rows and me.lower() not in {str(r.get("nick") or "").lower() for r in shop_rows}:
            return "refused", f"{me}: not in the shop channel (not a live seat)"
    free = free_seat_nicks(home, live)
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
                # FR #3400: orphan accepted under a departed seat — release then offer.
                acc_idx = None
                for i, row in enumerate(doc.get("accepted") or []):
                    if (
                        str(row.get("task") or "").upper() == task_u
                        and str(row.get("id") or "").strip().lstrip("#") == num
                        and repo_match(repo, str(row.get("repo") or ""))
                    ):
                        acc_idx = i
                        break
                if acc_idx is None:
                    return "refused", f"{repo}#{num} {task_u}: not in the unaccepted queue"
                holder = _accepted_holder_nick(doc["accepted"][acc_idx])
                if holder.lower() in live_l:
                    return (
                        "refused",
                        f"{repo}#{num} {task_u}: accepted by live seat {holder}",
                    )
                _release_accepted_for_nick_unlocked(doc, holder)
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
            if row_needs_human(cand, me):
                return "refused", "row is needs-human"
            if row_awaits_mrb1(cand):
                # Unreachable while row_awaits_mrb1 is always False (op 2026-10-04).
                return "refused", "row awaits needs-mrb1 clear (legacy)"
            if row_on_cooldown(cand, now_f, me):
                return "refused", "row is on GIVEUP/NACK cooldown"
            if row_skip_fr_reason(cand):
                return "refused", f"row skipped: {row_skip_fr_reason(cand)}"
            if repo_archived_for_queue(str(cand.get("repo") or "")):
                return "refused", "repo is archived (FR #785)"
            if row_machine_mismatch(cand, me):
                return "refused", f"row is pinned to another machine than {me}"
            if row_gave_up_by(cand, me):
                return "refused", f"{me} already gave this row up"
            why = ledger_blocks(ledger_load(home), cand, me, live)
            if why:
                return "refused", why
            if task_u == "FR" and fr_is_superseded(doc, str(cand.get("repo") or ""), str(cand.get("id") or "")):
                return "refused", "FR superseded by an open PR"
            if task_u == "FR" and not fr_row_offerable(
                cand, is_pull=is_pull, pr_exists=pr_exists, issue_open=issue_open
            ):
                return "refused", "row is a pull or CLOSED issue (not an offerable FR; #846/#838/#2340)"
            # FR #818 / t853u: refuse manual assign of legacy per-PR / non-#0 UAT.
            if task_u == "UAT" and not is_repo_uat(cand):
                return "refused", "UAT is per-repo only (id #0 + repo_uat); per-PR UAT forbidden (t853u / FR #818)"
            # FR #740 / #738 / #1585: refuse already-DONE MRB unless the pull is still open.
            if task_u == "MRB" and mrb_already_done(doc, cand, home=home, pr_exists=pr_exists):
                return "refused", "MRB already DONE for this repo+#id (FR #740)"
            if not mrb_row_offerable(cand, pr_exists=pr_exists):
                return "refused", "MRB has no real open pull URL"
            if review_blocked_for_author(cand, me, live, ledger=ledger_load(home), free=free):
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
    FR #2899: heal missing MRB ``/pull/N`` URLs before dropping; return ``dropped_detail``.
    """
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return {"ok": False, "error": "load"}
            before = len(doc["unaccepted"])
            keep = []
            dropped_detail: list[str] = []
            for row in doc["unaccepted"]:
                task = str(row.get("task") or "").upper()
                if task == "FR" and row_skip_fr_reason(row):
                    dropped_detail.append(f"{_row_drop_label(row)} skip_fr")
                    continue
                # FR #846: drop FR rows whose URL is a pull request.
                if task == "FR" and not fr_row_offerable(row):
                    dropped_detail.append(f"{_row_drop_label(row)} fr_not_offerable")
                    continue
                # FR #785: drop rows whose repo is archived / superseded (e.g. gh-Jeeves).
                if repo_archived_for_queue(str(row.get("repo") or "")):
                    dropped_detail.append(f"{_row_drop_label(row)} archived_repo")
                    continue
                # FR #595 / #2604 / #2899: heal missing pull URL before dropping.
                if task == "MRB":
                    _heal_mrb_pull_url(row)
                    if not mrb_row_offerable(row):
                        dropped_detail.append(f"{_row_drop_label(row)} mrb_not_offerable")
                        continue
                # FR #818 / t853u: drop any UAT that is not the single repo-level #0 row.
                if task == "UAT" and not is_repo_uat(row):
                    dropped_detail.append(f"{_row_drop_label(row)} uat_not_repo_level")
                    continue
                keep.append(row)
            doc["unaccepted"] = keep
            dropped = before - len(keep)
            try:
                _write_queue(queue_path(home), doc)
            except OSError:
                return {"ok": False, "error": "write"}
            return {
                "ok": True,
                "dropped": dropped,
                "dropped_detail": dropped_detail,
                "unaccepted": len(keep),
            }
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

    Merge, not wipe (the chair runs this hourly / on webhook gap — FR #3212):
    * rows of other kinds (UAT/BUILD/FIX/PR), ``accepted`` jobs, and rows of repos whose fetch FAILED are kept;
    * a stale FR/MRB row of a successfully fetched repo (closed/merged/superseded) is dropped;
    * safe-to-close/umbrella/board issues are never (re)added and are pruned from unaccepted (FR #180);
    * skill/harvest receipts ARE added as FR promote jobs (FR #1682 / #1684; operator 2026-10-04);
    * existing rows keep their seq/offer fields; new items are appended; repos in ``ignored`` are skipped.
    * ``NotModified`` / 304 from a budgeted ETag getter leaves that repo's rows untouched (not failed).

    ``token`` (optional) is sent as ``Authorization: Bearer``; it is never logged or returned.
    ``fetch_json(url) -> dict|list`` is the test seam; default is urllib with the token.
    """
    import urllib.request
    import github_api_budget as gab

    def _default_fetch(url: str):
        hdrs = {"Accept": "application/vnd.github+json", "User-Agent": "bobiverse-jeeves"}
        if token:
            hdrs["Authorization"] = "Bearer " + token
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    getter = fetch_json or _default_fetch

    def _fetch_all_pages(url_base: str, *, per_page: int = 100, max_pages: int = 20) -> list:
        """Follow GitHub list pagination (FR #1149 / #1444). One page left 100+ open issues off-queue."""
        out: list = []
        for page in range(1, max_pages + 1):
            sep = "&" if "?" in url_base else "?"
            chunk = getter(f"{url_base}{sep}per_page={per_page}&page={page}")
            if not isinstance(chunk, list):
                break
            out.extend(chunk)
            if len(chunk) < per_page:
                break
        return out

    skip = {str(x).strip().lower() for x in (ignored or ()) if str(x).strip()}
    desired: list[GitClaim] = []
    fetched: list[str] = []
    failed: list[str] = []
    open_pulls_map: dict[str, set[str]] = {}
    skipped_draft = 0
    # FR #2899: open pulls skipped from desired (draft/receipt) — do not "survive" keep.
    skipped_open_pulls: set[tuple[str, str]] = set()
    # FR #2389: only *merged* closers remove an issue from desired. Open Closes-PRs
    # stay as MRB rows; the open issue stays desired so fr_done can clear and MRB
    # (or a re-opened FR if MRB is missing) can flow. (Open-PR supersede for offer
    # still happens via fr_is_superseded once the MRB row is queued.)
    supersede_keys: set[str] = set()  # owner/repo#N closed by merged PR Closes only
    closed_by_merged_pr: set[str] = set()  # #N ids closed by merged PRs (same-repo)
    repo_clear: dict[str, bool] = {}   # t853u: no open non-excluded issue and no open PR
    uat_plan: dict[str, tuple[list[str], list[str]]] = {}   # repo -> (merged PRs this cycle, issues they closed)
    cycles = ledger_load(home).get("uat_cycle") or {}
    for repo in repos:
        if not REPO_RE.fullmatch(repo):
            continue
        if repo.lower() in skip or repo.split("/", 1)[-1].lower() in skip:
            continue
        # FR #785: never resync an archived/superseded source (use successor via discover rewrite).
        if repo_archived_for_queue(repo):
            continue
        try:
            issues = _fetch_all_pages(
                f"https://api.github.com/repos/{repo}/issues?state=open"
            )
            prs = _fetch_all_pages(
                f"https://api.github.com/repos/{repo}/pulls?state=open"
            )
        except gab.NotModified:
            # FR #3212: ETag/304 — repo unchanged; keep prior rows (do not mark fetched or failed).
            continue
        except Exception:  # noqa: BLE001 - one bad repo (404/403/rate limit) must not wipe its rows
            failed.append(repo)
            continue
        fetched.append(repo)
        if not isinstance(issues, list):
            issues = []
        if not isinstance(prs, list):
            prs = []
        # t853u: repo-level UAT gate. Excluded issues (needs-human, boards/mrb-home, harvest/skill
        # records, CRITICAL spam, safe-to-close, needs-mrb1 — FR #1416) never hold a repo back;
        # every other open issue or any open PR does.
        blocking = [
            i for i in issues
            if isinstance(i, dict) and not i.get("pull_request") and issue_blocks_repo_uat(
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
                title = str(pr.get("title") or "")
                # bobiverse#765 / #781: mrb-*-fix merges are not UAT cycle inputs.
                if is_mrb_fix_pr_title(title):
                    continue
                merged.append(f"#{pr['number']}")
                for r in extract_closes_issue_ids(title, str(pr.get("body") or ""), repo=repo):
                    if r not in linked:
                        linked.append(r)
            if merged:
                uat_plan[repo] = (merged, linked)
                # FR #2389: merged closers (recent cycle) remove issues from desired.
                for r in linked:
                    closed_by_merged_pr.add(r)
                for iss_id in linked:
                    # extract_closes may return #N; also stamp owner/repo#N supersede keys.
                    n = str(iss_id).lstrip("#")
                    if n.isdigit():
                        supersede_keys.add(f"{repo}#{n}")
        for pr in prs:
            if not isinstance(pr, dict):
                continue
            num = pr.get("number")
            if not isinstance(num, int):
                continue
            title = str(pr.get("title") or "")
            body = str(pr.get("body") or "")
            refs = extract_closes_issue_ids(title, body, repo=repo)
            # FR #2389: do NOT add open-PR Closes refs to closed_by_merged_pr / supersede_keys.
            # That left open issues out of desired, so fr_done never cleared (#2380/#2383 class).
            open_pulls_map.setdefault(repo, set()).add(f"#{num}")
            # bobiverse#224 / #781: open mrb-*-fix PRs are not MRB queue jobs.
            if is_mrb_fix_pr_title(title):
                continue
            # FR #2604: draft open PRs must not become MRB jobs; still count as open
            # for UAT/repo_clear and FR supersede via open_pulls_map above.
            if pr.get("draft") is True:
                skipped_draft += 1
                skipped_open_pulls.add((repo, f"#{num}"))
                print(
                    f"resync skip draft PR {repo}#{num}",
                    flush=True,
                )
                continue
            # FR #2650: intake harvest receipt PRs (even non-draft) never become MRB.
            pr_labels = _label_names(pr.get("labels"))
            if is_intake_harvest_receipt_pr(title=title, body=body, labels=pr_labels):
                skipped_draft += 1
                skipped_open_pulls.add((repo, f"#{num}"))
                print(
                    f"resync skip harvest-receipt PR {repo}#{num}",
                    flush=True,
                )
                continue
            lesson = is_harvest_lesson_pr(title=title, labels=pr_labels)
            desired.append(
                GitClaim(
                    repo=repo,
                    task="MRB",
                    id=f"#{num}",
                    event="pull_request",
                    action="opened",
                    line="",
                    refs=() if lesson else refs,
                    harvest_lesson=lesson,
                    opened_by=lesson_pr_opener_seat(body) if lesson else "",
                )
            )
        for iss in issues:
            if not isinstance(iss, dict) or iss.get("pull_request"):
                continue
            num = iss.get("number")
            if not isinstance(num, int):
                continue
            ident = f"#{num}"
            if ident in closed_by_merged_pr:
                continue
            if fr_issue_key(repo, ident) in supersede_keys:
                continue  # FR #254 / #2389: merged Closes only
            title = str(iss.get("title") or "")
            body = str(iss.get("body") or "")
            labels = _label_names(iss.get("labels"))
            state = str(iss.get("state") or "open")
            if issue_skip_fr_reason(title=title, body=body, labels=labels, state=state):
                continue
            if (str(repo).lower(), _norm_row_id(ident)) in _SKIP_FR_ISSUE_PINS:
                continue  # FR #2480 hard-pin umbrella
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
            want = {(c.repo, c.task, _norm_row_id(c.id)) for c in desired}
            fetched_set = set(fetched)
            before = len(doc["unaccepted"])
            keep = []
            dropped_detail: list[str] = []
            for row in doc["unaccepted"]:
                task_u = str(row.get("task") or "").upper()
                repo_s = str(row.get("repo") or "")
                ident_n = _norm_row_id(row.get("id"))
                if task_u == "UAT":
                    # FR #818 / t853u: only keep real repo-level UAT (#0 + repo_uat).
                    if not is_repo_uat(row):
                        dropped_detail.append(f"{_row_drop_label(row)} uat_not_repo_level")
                        continue
                    if (
                        row.get("repo") in fetched_set
                        and not repo_clear.get(str(row.get("repo")), True)
                    ):
                        # FR #2971: drop even when offered_to is set — sticky shop
                        # offers must not survive after a blocking FR opens.
                        dropped_detail.append(f"{_row_drop_label(row)} uat_repo_not_clear")
                        continue  # new issue / PR opened: the repo is no longer clear, UAT waits
                if task_u == "FR" and row_skip_fr_reason(row):
                    dropped_detail.append(f"{_row_drop_label(row)} skip_fr")
                    continue  # FR #180 local junk
                if task_u == "FR" and not fr_row_offerable(row):
                    dropped_detail.append(f"{_row_drop_label(row)} fr_not_offerable")
                    continue  # FR #846: /pull/ URL is never an FR
                if task_u == "FR" and fr_is_superseded(
                    doc,
                    repo_s,
                    str(row.get("id") or ""),
                    open_pulls=open_pulls_map,
                    fetched_repos=set(fetched),
                ):
                    dropped_detail.append(f"{_row_drop_label(row)} fr_superseded")
                    continue  # FR #254
                # FR #846: drop FR whose id is an open pull number for this repo.
                if task_u == "FR":
                    if ident_n in (open_pulls_map.get(repo_s) or set()):
                        dropped_detail.append(f"{_row_drop_label(row)} fr_is_open_pull")
                        continue
                if (
                    repo_s in fetched_set
                    and task_u == "FR"
                    and (repo_s, "FR", ident_n) not in want
                ):
                    # FR #846: do not preserve closed-issue / closed-PR phantoms via offered_to.
                    dropped_detail.append(f"{_row_drop_label(row)} fr_not_in_want")
                    continue
                if (
                    repo_s in fetched_set
                    and task_u in ("FR", "MRB")
                    and (repo_s, task_u, ident_n) not in want
                    and not mrb_row_should_survive_resync(
                        row, want=want, fetched=fetched_set
                    )
                ):
                    # FR #2899: still-open pull that missed desired (label race / transient
                    # want miss) must survive — unless this cycle classified it draft/receipt.
                    if (
                        task_u == "MRB"
                        and ident_n in (open_pulls_map.get(repo_s) or set())
                        and (repo_s, ident_n) not in skipped_open_pulls
                    ):
                        _heal_mrb_pull_url(row, force=True)
                        keep.append(row)
                        continue
                    # FR #1323 / #2458: drop MERGED/closed even when offered_to is set
                    dropped_detail.append(f"{_row_drop_label(row)} not_in_want")
                    continue
                # FR #1323 / #1585: drop ledger-held MRB only when GitHub no longer wants it.
                # Open pulls in ``want`` must survive keep so offered_to/seq are preserved;
                # stale mrb_done stamps are cleared below when re-enqueueing desired MRBs.
                if (
                    task_u == "MRB"
                    and mrb_ledger_done_hold(home, repo_s, ident_n)
                    and (repo_s, "MRB", ident_n) not in want
                    and not (
                        ident_n in (open_pulls_map.get(repo_s) or set())
                        and (repo_s, ident_n) not in skipped_open_pulls
                    )
                ):
                    dropped_detail.append(f"{_row_drop_label(row)} mrb_ledger_done")
                    continue
                keep.append(row)
            dropped = before - len(keep)
            doc["unaccepted"] = keep
            # FR #2458: belt-and-suspenders — drop MRB absent from open pulls for fetched repos
            # (covers id-shape / offered_to edge cases the keep loop may miss).
            # Do not pass home here: without an open-PR checker, ledger mrb_done would
            # re-kill still-open rows (FR #1585). open_pulls alone is the truth for this pass.
            purged_n = _purge_dead_mrb_unaccepted(
                doc,
                open_pulls=open_pulls_map,
                fetched_repos=fetched_set,
            )
            if purged_n:
                dropped += purged_n
                dropped_detail.append(f"purge_dead_mrb x{purged_n}")
            added = 0
            fetched_set2 = set(fetched)
            # Premature DONE while GitHub issue/PR still open: pull those rows out of done
            # so resync can re-queue them (FR #1150 / #1444).
            # FR #2617: keep DONE FR rows that carry a /pull/ URL while that implement PR
            # is still open (or its repo was not fetched). Stripping them broke
            # fr_superseded_by_done_pr and let the FR re-enter unaccepted right after DONE.
            if isinstance(doc.get("done"), list):
                still_open = {(c.repo, c.task, c.id) for c in desired}
                kept_done: list = []
                for r in doc["done"]:
                    if not isinstance(r, dict):
                        continue
                    key = (
                        str(r.get("repo") or ""),
                        str(r.get("task") or ""),
                        str(r.get("id") or ""),
                    )
                    if key not in still_open:
                        kept_done.append(r)
                        continue
                    if str(r.get("task") or "").upper() == "FR":
                        parsed = parse_github_pull_url(str(r.get("url") or ""))
                        if parsed:
                            pr_repo, pr_id = parsed
                            if pr_repo not in fetched_set2:
                                kept_done.append(r)
                                continue
                            if pr_id in (open_pulls_map.get(pr_repo) or set()):
                                kept_done.append(r)
                                continue
                    # Drop premature DONE (issue/PR still open, no open implement PR).
                doc["done"] = kept_done
            ledger_now = ledger_load(home)

            def _fr_done_hold(repo: str, ident: str) -> bool:
                # Ledger fr_done means a seat already DONE'd this FR (PR may be in MRB).
                # Hold only while the FR is *not* in the GitHub want set — if desired still
                # lists it, no open PR Closes it, so suppressing enqueue stranded open
                # issues (e.g. #1201) and Jeeves reported empty while GitHub showed work.
                done_ts = _parse_iso_ts(
                    str((ledger_now.get("fr_done") or {}).get(_lkey(repo, ident)) or "")
                )
                return done_ts is not None and (time.time() - done_ts) < FR_DONE_HOLD_S

            # Drop stale unaccepted FR rows that are still inside the hold *and* not wanted
            # by GitHub (PR open / issue closed). Wanted FRs must stay enqueueable.
            want_fr = {(c.repo, c.id) for c in desired if c.task == "FR"}
            doc["unaccepted"] = [
                r
                for r in doc["unaccepted"]
                if not (
                    isinstance(r, dict)
                    and str(r.get("task") or "").upper() == "FR"
                    and _fr_done_hold(str(r.get("repo") or ""), str(r.get("id") or ""))
                    and (str(r.get("repo") or ""), str(r.get("id") or "")) not in want_fr
                )
            ]
            cleared_fr_done: list[str] = []
            cleared_mrb_done: list[str] = []
            for claim in desired:
                # FR #2389 / #1201 / #1482: clear fr_done for every desired open issue even when
                # fr_is_superseded skips re-enqueue (open Closes-PR → MRB). Otherwise the stamp
                # sticks 24h while the issue stays OPEN with no merged closer.
                if claim.task == "FR":
                    fk = _lkey(claim.repo, claim.id)
                    if fk in (ledger_now.get("fr_done") or {}):
                        cleared_fr_done.append(fk)
                if claim.task == "FR" and fr_is_superseded(
                    doc,
                    claim.repo,
                    claim.id,
                    open_pulls=open_pulls_map,
                    fetched_repos=fetched_set2,
                ):
                    continue  # FR #254: MRB / open implement PR supersedes FR enqueue
                # FR #1585: open PR still on GitHub — clear premature mrb_done so offer
                # purge cannot wipe the row resync just (re)queued.
                if claim.task == "MRB":
                    mk = _lkey(claim.repo, claim.id)
                    if mk in (ledger_now.get("mrb_done") or {}):
                        cleared_mrb_done.append(mk)
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
                    # FR #1093: refresh title/body/labels and stamp require_machine on stale rows
                    # (resync used to skip already-queued FRs, so WP0 pins never landed).
                    # FR #3277: heal missing author_seat/implementer_seat from DONE FR / Closes refs.
                    author_extra = mrb_author_extra_from_doc(doc, claim) if claim.task == "MRB" else {}
                    for r in doc["unaccepted"]:
                        if not _same(r, claim.repo, claim.task, claim.id):
                            continue
                        if claim.title:
                            r["title"] = claim.title
                        if claim.body:
                            r["body"] = claim.body
                        if claim.labels:
                            r["labels"] = list(claim.labels)
                        if claim.harvest_lesson:
                            _heal_lesson_mrb_row(r, claim.opened_by)
                        elif author_extra and not row_author_seats(r):
                            for k, v in author_extra.items():
                                if v:
                                    r[k] = v
                        _stamp_require_machine(r, claim)
                    # Clear *stale* needs_human (keep-the-flow) but keep the intentional
                    # FR #180 gate after GIVEUP_NEEDS_HUMAN_COUNT giveups.
                    for r in doc["unaccepted"]:
                        if not _same(r, claim.repo, claim.task, claim.id):
                            continue
                        if not r.get("needs_human"):
                            continue
                        if int(r.get("giveup_count") or 0) >= GIVEUP_NEEDS_HUMAN_COUNT:
                            continue
                        r.pop("needs_human", None)
                    continue
                extra_add: dict[str, str] = {}
                if mrb_url:
                    extra_add["url"] = mrb_url
                if claim.task == "MRB":
                    extra_add.update(mrb_author_extra_from_doc(doc, claim))
                if _append_unaccepted(doc, claim, **extra_add) == "added":
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
            # FR #1508: drop focus items for closed issues/PRs so strict focus
            # reflects open ungated work (not a graveyard of closed ranks).
            try:
                import focus_ignore as _fi

                open_keys = set()
                for c in desired:
                    open_keys.add(f"{c.repo}{c.id}".lower())
                for repo, nums in (open_pulls_map or {}).items():
                    for num in nums or ():
                        n = str(num).lstrip("#")
                        open_keys.add(f"{repo}#{n}".lower())
                focus_pruned = _fi.prune_closed_focus_items(home, open_keys)
                # FR #1520: drop owner/repo#N items when that repo is already focused.
                focus_redundant = _fi.prune_redundant_focus_items(home)
            except Exception:
                focus_pruned = 0
                focus_redundant = 0
            _write_queue(queue_path(home), doc)
            # FR #3205: refresh ordered offer candidates off the IRC thread (resync path).
            with contextlib.suppress(Exception):
                rebuild_offer_precompute(home, list(doc.get("unaccepted") or []))
            if cleared_fr_done or cleared_mrb_done:
                def _clear_stale_done_stamps(led: dict) -> None:
                    if cleared_fr_done:
                        fd = led.setdefault("fr_done", {})
                        for k in cleared_fr_done:
                            fd.pop(k, None)
                    if cleared_mrb_done:
                        md = led.setdefault("mrb_done", {})
                        for k in cleared_mrb_done:
                            md.pop(k, None)

                with contextlib.suppress(OSError):
                    _ledger_update(home, _clear_stale_done_stamps)
            return {
                "ok": True,
                "unaccepted": len(doc["unaccepted"]),
                "added": added,
                "dropped": dropped,
                "dropped_detail": list(dropped_detail),
                "skipped_draft": int(skipped_draft),
                "focus_pruned": int(focus_pruned),
                "focus_redundant": int(focus_redundant),
                "repos": list(fetched),
                "failed": list(failed),
            }
    except (TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


def _offer_age_s(row: dict, now: float) -> float:
    """Seconds since ``offered_ts`` (or +inf when missing/unparseable)."""
    try:
        return float(now) - datetime.fromisoformat(
            str(row.get("offered_ts") or "").replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        return OFFER_TIMEOUT_S + 1.0


def seat_pending_offer(home: Path, nick: str, now: float | None = None) -> dict | None:
    """FR #3192: live unaccepted row still offered to this nick within ``OFFER_TIMEOUT_S``."""
    import time as _time

    now_f = _time.time() if now is None else float(now)
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return None
    try:
        doc = load_queue(home)
    except Exception:  # noqa: BLE001
        return None
    for row in doc.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        to = str(row.get("offered_to") or "").strip()
        if not to:
            continue
        them = (canonical_worker_nick(to) or to).strip().lower()
        if them != me:
            continue
        if _offer_age_s(row, now_f) < OFFER_TIMEOUT_S:
            return row
    return None


def should_drop_stale_bored(
    home: Path,
    nick: str,
    now: float | None = None,
    *,
    except_job: dict | None = None,
) -> bool:
    """FR #3192: drop a !bored reply when the seat already ACKed or still holds an offer.

    Used after slow GitHub work on the IRC thread so a late offer does not land on a seat
    that accepted (or was assigned) while the offer was being computed.

    ``except_job``: when called *after* ``offer_focus_top`` stamped a new offer, pass that
    job so the just-stamped row does not count as a pre-existing pending offer.
    """
    import time as _time

    now_f = _time.time() if now is None else float(now)
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    try:
        for row in load_accepted(home):
            if not isinstance(row, dict):
                continue
            raw = str(
                row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
            ).strip()
            them = (canonical_worker_nick(raw) or raw).strip().lower()
            if them == me:
                return True
    except Exception:  # noqa: BLE001
        return False
    pending = seat_pending_offer(home, nick, now_f)
    if not pending:
        return False
    if except_job is not None and _same(
        pending,
        str(except_job.get("repo") or ""),
        str(except_job.get("task") or ""),
        str(except_job.get("id") or ""),
    ):
        return False
    return True


def clear_seat_offer(
    home: Path,
    nick: str,
    job: dict,
) -> bool:
    """FR #3192: unstamp a just-made offer when the stale-bored drop fires after stamp."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me or not isinstance(job, dict):
        return False
    repo = str(job.get("repo") or "")
    task = str(job.get("task") or "")
    jid = str(job.get("id") or "")
    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            changed = False
            for cand in doc.get("unaccepted") or []:
                if not isinstance(cand, dict):
                    continue
                if not _same(cand, repo, task, jid):
                    continue
                to = str(cand.get("offered_to") or "").strip()
                them = (canonical_worker_nick(to) or to).strip().lower()
                if them != me:
                    continue
                cand.pop("offered_to", None)
                cand.pop("offered_ts", None)
                cand.pop("offered_channel", None)
                cand.pop("offered_via", None)
                changed = True
            if changed:
                _write_queue(queue_path(home), doc)
            return changed
    except Exception:  # noqa: BLE001
        return False


def _seat_has_accepted(home: Path, nick: str) -> bool:
    """True when the accepted queue still lists this nick (ACK landed)."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    try:
        for row in load_accepted(home):
            if not isinstance(row, dict):
                continue
            raw = str(
                row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
            ).strip()
            them = (canonical_worker_nick(raw) or raw).strip().lower()
            if them == me:
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


def bored_gate(home: Path, nick: str, channel: str, now: float) -> str:
    """ignore, wait, busy, or ok. wait is checked before busy so retries stay quiet."""
    shop = worker_shop_channel(nick)
    if shop is None or _channel(channel) != shop:
        return "ignore"
    last = last_worker_activity(home, nick)
    if last is not None and (float(now) - last) < IDLE_S:
        return "wait"
    # FR #3192: outstanding offered_to (pending ACK / undelivered assign) is busy —
    # never re-offer the same row and never treat it as stale digest doing.
    if seat_pending_offer(home, nick, now):
        return "busy"
    # FR #3192: accepted row is busy even before digest on_ack paints working_on
    # (stale !bored after slow GH work must NAK-busy, not stamp a second offer).
    if _seat_has_accepted(home, nick):
        if release_stale_busy(home, nick, now):
            return "ok"
        return "busy"
    if worker_working_on(home, nick):
        if release_stale_busy(home, nick, now):
            return "ok"
        return "busy"
    return "ok"


# A seat only sends !bored when it is idle. If the digest still says "doing" but the seat has
# no accepted queue row, or its accepted row is older than BUSY_STALE_S, the DONE was lost:
# nak-busying it forever stalls the whole fleet (2026-10-05: marchhare seats nak-busy 8h on
# merged MRB #2349 / closed FR #2340 while every open MRB was ionos-authored).
BUSY_STALE_S = 3600.0


def release_stale_busy(home: Path, nick: str, now: float) -> bool:
    """Heal a lost-DONE seat on !bored: drop its stale accepted row(s), set it idle. True if healed."""
    me = (canonical_worker_nick(nick) or nick or "").strip().lower()
    if not me:
        return False
    # FR #3192: assigned/offered-but-not-ACKed is not stale busy — keep digest doing.
    if seat_pending_offer(home, nick, now):
        return False

    def _owner(r: dict) -> str:
        # Match ACC purge seats (#2361): nick / accepted_by / offered_to.
        raw = str(
            r.get("nick") or r.get("accepted_by") or r.get("offered_to") or ""
        ).strip()
        return (canonical_worker_nick(raw) or raw).strip().lower()

    try:
        with _lock(home):
            doc = _load_queue_unlocked(home)
            # Re-check pending offer under the lock (race with assign / offer_focus_top).
            for cand in doc.get("unaccepted") or []:
                if not isinstance(cand, dict):
                    continue
                to = str(cand.get("offered_to") or "").strip()
                if not to:
                    continue
                them = (canonical_worker_nick(to) or to).strip().lower()
                if them == me and _offer_age_s(cand, float(now)) < OFFER_TIMEOUT_S:
                    return False
            acc = [r for r in (doc.get("accepted") or []) if isinstance(r, dict)]
            mine = [r for r in acc if _owner(r) == me]
            for r in mine:
                ts = str(r.get("accepted_ts") or r.get("offered_ts") or r.get("ts") or "")
                try:
                    age = float(now) - datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    age = BUSY_STALE_S + 1
                if age < BUSY_STALE_S:
                    return False  # genuinely recent job: honour busy
            if mine:
                # Drop (not requeue): github-resync re-adds the row if the item is still open,
                # so a closed/merged job is never handed out again.
                # Audit stamp (MRB #2373 / FR #2369): keep a done trail for stale busy releases.
                done = doc.setdefault("done", [])
                for r in mine:
                    fin = dict(r)
                    fin["result"] = "STALE_BUSY"
                    fin["done_ts"] = _utc_now()
                    done.append(fin)
                if len(done) > DONE_CAP:
                    doc["done"] = done[-DONE_CAP:]
                doc["accepted"] = [r for r in acc if _owner(r) != me]
                _write_queue(queue_path(home), doc)
    except Exception:  # noqa: BLE001
        return False
    try:
        out = bobreport.clear_seat_doing(_root(home), nick)
    except Exception:  # noqa: BLE001
        return False
    return bool(getattr(out, "ok", False))
