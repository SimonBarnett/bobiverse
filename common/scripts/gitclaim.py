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
    }
)

# Labels safe to detect in free text (title/line/body). Bare ``mrb`` is labels-only —
# otherwise titles like "harden MRB/FR routing" (#595) would false-positive.
SKIP_FR_LABELS_IN_TEXT = frozenset(
    lab for lab in SKIP_FR_LABELS if lab not in {"mrb", "skill"}
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
                for ref in claim.refs:
                    _remove_unaccepted_tasks(doc, claim.repo, ref, {"FR", "PR", "UAT"})
                extra = {}
                if claim.refs:
                    extra["refs"] = ",".join(claim.refs)
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
                "author_seat", "author_nick", "author", "implementer_seat", "mrb_author_seat", "mrb_fix_author_seat",
                "author_seats", "url", "title", "body", "state",
                "cooldown_until", "giveup_ts", "supersedes", "result", "done_ts", "done_by"):
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
    if row_needs_human(row):
        out["needs_human"] = True
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


def mrb_row_offerable(
    row: dict,
    *,
    pr_exists=None,
) -> bool:
    """True when an MRB row has a resolvable pull URL (and optional live PR check).

    FR #595 / #247: never offer MRB without a real ``/pull/N`` (or explicit pr_id).
    """
    if _canon_task(row) != "MRB":
        return True
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
    """Return ``pr_exists(repo, num)`` when a GitHub token is available (FR #595 / #247).

    Returns None when offline / no token (structural URL checks in
    ``mrb_row_offerable`` still apply).
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
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                ok = 200 <= int(getattr(resp, "status", 200) or 200) < 300
        except urllib.error.HTTPError as e:
            ok = False
            if int(getattr(e, "code", 0) or 0) not in (404, 410):
                pass  # non-404: still fail closed for offer
        except Exception:
            ok = False
        store[key] = ok
        return ok

    return _check


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



# FR #618 / #635: UAT of a PR number often lacks stamps (DONE MRB stamps the Closes issue id).
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
    """Find MRB accepted/done rows related to a UAT row (FR #618 / #635)."""
    repo = str(uat_row.get("repo") or "")
    uid = str(uat_row.get("id") or "")
    urefs = set(_row_refs_list(uat_row))
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
    """Copy UAT row with author stamps filled from related MRB rows when missing (FR #618 / #635).

    Chair often offers `UAT owner/repo#<PR>` while DONE MRB stamped `UAT #<issue>`.
    Without enrichment, the FR implementer / MRB reviewer is offered their own UAT.
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
            if v and not out.get(k):
                extras[k] = v
        fix_nick = _canon_seat_nick(str(mrb.get("nick") or mrb.get("done_by") or ""))
        if fix_nick and not out.get("mrb_fix_author_seat") and not extras.get("mrb_fix_author_seat"):
            blob = f"{out.get('line') or ''}\n{out.get('title') or ''}\n{out.get('id') or ''}".lower()
            mid = str(mrb.get("id") or "").lstrip("#")
            if mid and (f"mrb-{mid}" in blob or "nits" in blob or "fix(mrb" in blob):
                extras["mrb_fix_author_seat"] = fix_nick
    out.update(extras)
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
        # Exact author seat: block while any other seat is live (legacy MRB rule).
        if author_l == me_l:
            if live_c - {me_l}:
                return True
            continue
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
    try:
        with _lock(home):
            try:
                doc = _load_queue_unlocked(home)
            except (OSError, json.JSONDecodeError, ValueError):
                return "error", None
            order = ordered_unaccepted(home, doc["unaccepted"])
            pick = None
            for cand in order:
                if row_needs_human(cand) or row_on_cooldown(cand, now_f):
                    continue  # FR #180: GIVEUP/NACK cooldown / needs-human
                if row_skip_fr_reason(cand):
                    continue
                if str(cand.get("task") or "").upper() == "FR" and fr_is_superseded(
                    doc, str(cand.get("repo") or ""), str(cand.get("id") or "")
                ):
                    continue  # FR #254
                # FR #595 / #247: skip MRB without a real pull URL (or PR 404).
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
                cand_eff = enrich_uat_author_fields(doc, cand)
                if review_blocked_for_author(cand_eff, me, live):
                    continue
                pick = cand_eff
                break
            if pick is None:
                return "empty", None
            for i, row in enumerate(doc["unaccepted"]):
                if row is pick or _same(row, str(pick.get("repo") or ""), str(pick.get("task") or ""), str(pick.get("id") or "")):
                    # FR #618 / #635: persist enriched author stamps (pick may be enrich copy).
                    job = dict(pick)
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
            doc["unaccepted"].sort(key=_sort_key)
            pick_i = None
            for i, row in enumerate(doc["unaccepted"]):
                if row_needs_human(row) or row_on_cooldown(row, now_f) or row_skip_fr_reason(row):
                    continue
                if str(row.get("task") or "").upper() == "FR" and fr_is_superseded(
                    doc, str(row.get("repo") or ""), str(row.get("id") or "")
                ):
                    continue  # FR #254
                if not mrb_row_offerable(row, pr_exists=pr_exists):
                    continue
                row_eff = enrich_uat_author_fields(doc, row)
                live = live_seat_nicks(home)
                if review_blocked_for_author(row_eff, (nick or "").strip(), live):
                    continue
                pick_i = i
                # Persist enrichment onto the queued row when we filled stamps.
                if row_eff is not row:
                    doc["unaccepted"][i] = dict(row_eff)
                break
            if pick_i is None:
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
                if any(_same(r, claim.repo, claim.task, claim.id) for r in doc["accepted"] + doc["unaccepted"]):
                    continue                      # already queued/claimed: keep its line, seq and offer fields
                if _append_unaccepted(doc, claim) == "added":
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
