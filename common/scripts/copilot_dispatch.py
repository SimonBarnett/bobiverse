"""FR #5170: Jeeves Copilot Coding Agent virtual seat (deterministic, no LLM).

CCA runs on GitHub cloud. Jeeves POSTs ``agents/repos/{owner}/{repo}/tasks``
with a ``prompt`` field (not ``problem_statement``), tracks the task + PR
webhooks instead of IRC ACK/DONE, and falls back to shop seats when allowance
is exhausted.
"""
from __future__ import annotations

import contextlib

import json
import logging
import os
import re
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import bobreport
import gitclaim
import shop_listen

log = logging.getLogger("copilot_dispatch")

COPILOT_NICK = "copilot"
GIT_HOOK_URL = "https://bob.ntsa.uk/bob/v1/git"
REQUIRED_HOOK_EVENTS = (
    "issues",
    "issue_comment",
    "pull_request",
    "pull_request_review",
    "push",
    "check_suite",
    "check_run",
    "workflow_run",
)
ALLOWANCE_NAME = "copilot-allowance.json"
JOBS_NAME = "copilot-jobs.json"
TASK_TIMEOUT_S = 4 * 3600.0
CACHE_S = 300.0
COPILOT_COOLDOWN_S = 7 * 86400.0
FUEL_COOLDOWN_S = {
    "copilot": COPILOT_COOLDOWN_S,
    "cursor": COPILOT_COOLDOWN_S,
    "grok": COPILOT_COOLDOWN_S,
}
COPILOT_USER_PATH = "copilot_internal/user"
FALLBACK_REASONS = frozenset(
    {"startup", "webhook_gap", "delivery_failure", "safety_interval", "operator"}
)


def tasks_api_path(repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"agents/repos/{owner}/{name}/tasks"


def _jobs_path(home: Path) -> Path:
    return Path(home) / JOBS_NAME


def _allow_path(home: Path) -> Path:
    return Path(home) / ALLOWANCE_NAME


def load_allowance(home: Path) -> dict:
    p = _allow_path(home)
    if not p.is_file():
        return {"remaining": None, "exhausted": False}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"remaining": None, "exhausted": False}
    return doc if isinstance(doc, dict) else {"remaining": None, "exhausted": False}


def _clear_copilot_cooldown(doc: dict) -> None:
    """Drop the legacy cooldown and the FR #5397 per-fuel copilot block."""
    doc.pop("exhausted_until", None)
    doc.pop("exhausted_until_utc", None)
    doc.pop("pause_announced_until", None)
    fuels = doc.get("fuels")
    if not isinstance(fuels, dict):
        return
    block = fuels.get("copilot")
    if not isinstance(block, dict):
        return
    block = dict(block)
    block.pop("exhausted_until", None)
    block.pop("exhausted_until_utc", None)
    if block:
        fuels["copilot"] = block
    else:
        fuels.pop("copilot", None)
    doc["fuels"] = fuels


def set_allowance(home: Path, remaining: int | None = None, exhausted: bool | None = None) -> None:
    doc = load_allowance(home)
    if remaining is not None:
        doc["remaining"] = int(remaining)
        doc["exhausted"] = int(remaining) <= 0
        if int(remaining) > 0:
            doc["tasks_exhausted"] = False
            doc["state"] = "ok"
            _clear_copilot_cooldown(doc)
    if exhausted is not None:
        doc["exhausted"] = bool(exhausted)
        if not exhausted:
            doc["tasks_exhausted"] = False
            _clear_copilot_cooldown(doc)
    Path(home).mkdir(parents=True, exist_ok=True)
    _allow_path(home).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _num(val: object) -> float | None:
    if val is None or val is True or val is False:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_user_quota(doc: dict | None) -> dict:
    """Parse GET /copilot_internal/user. Bad shape is unknown, never exhausted."""
    empty = {
        "plan": "",
        "used": None,
        "remaining": None,
        "unlimited": False,
        "percent_remaining": None,
        "reset_at": "",
        "source": "copilot_internal/user",
        "state": "unknown",
        "fetched_at": "",
    }
    if not isinstance(doc, dict):
        return dict(empty)
    snaps = doc.get("quota_snapshots")
    prem = snaps.get("premium_interactions") if isinstance(snaps, dict) else None
    if not isinstance(prem, dict):
        out = dict(empty)
        out["plan"] = str(doc.get("copilot_plan") or "")
        return out
    unlimited = bool(prem.get("unlimited"))
    remaining = _num(prem.get("remaining"))
    percent = _num(prem.get("percent_remaining"))
    used = _num(prem.get("credits_used"))
    allowed = unlimited or (remaining is not None and remaining > 0) or (
        percent is not None and percent > 0
    )
    state = "ok" if allowed else "exhausted"
    return {
        "plan": str(doc.get("copilot_plan") or ""),
        "used": used,
        "remaining": remaining,
        "unlimited": unlimited,
        "percent_remaining": percent,
        "entitlement": _num(prem.get("entitlement")),
        "overage_permitted": bool(prem.get("overage_permitted")),
        "reset_at": str(doc.get("quota_reset_date_utc") or doc.get("quota_reset_date") or ""),
        "source": "copilot_internal/user",
        "state": state,
        "fetched_at": "",
    }


def _reset_passed(doc: dict) -> bool:
    reset = str(doc.get("reset_at") or "")
    if not reset:
        return False
    try:
        from datetime import datetime, timezone

        end = datetime.fromisoformat(reset.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) >= end
    except ValueError:
        return False


def allowance_from_pool(doc: dict) -> bool:
    if not isinstance(doc, dict):
        return False
    if doc.get("tasks_exhausted") and not _reset_passed(doc):
        return False
    if doc.get("unlimited"):
        return True
    if str(doc.get("state") or "") == "unknown":
        return False  # FR #5174: fail closed (do not steal IRC jobs)
    rem = _num(doc.get("remaining"))
    pct = _num(doc.get("percent_remaining"))
    if rem is not None and rem > 0:
        return True
    if pct is not None and pct > 0:
        return True
    if rem == 0 or str(doc.get("state") or "") == "exhausted":
        return False
    if doc.get("exhausted") and rem is None:
        return False
    return False


def fuel_cooldown_seconds(fuel: str = "copilot") -> float:
    return float(FUEL_COOLDOWN_S.get((fuel or "copilot").strip().lower(), COPILOT_COOLDOWN_S))


def parse_quota_reset_epoch(value: object) -> float | None:
    """FR #5515: quota_reset_date / quota_reset_date_utc -> 00:00 UTC that calendar day."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        from datetime import datetime, timezone

        s = raw.replace("Z", "+00:00")
        if "T" not in s:
            s = s + "T00:00:00+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        midnight = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
        return midnight.timestamp()
    except ValueError:
        return None


def first_of_next_month_utc(now: float) -> float:
    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(float(now), tz=timezone.utc)
    if dt.month == 12:
        nxt = datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        nxt = datetime(dt.year, dt.month + 1, 1, tzinfo=timezone.utc)
    return nxt.timestamp()


def quota_pause_until(
    now: float,
    *,
    reset_date: object = None,
    fuel: str = "copilot",
) -> tuple[float, str]:
    """FR #5515: Copilot pauses until API reset date, else 1st of next month.

    Other fuels keep the FR #5316 seven-day pause unless a reset date is given.
    """
    parsed = parse_quota_reset_epoch(reset_date)
    now_f = float(now)
    # Stale API date (midnight already passed, e.g. token-out on the 1st) must
    # not unpause immediately; fall through like a missing date.
    if parsed is not None and parsed > now_f:
        return parsed, "api"
    name = _fuel_name(fuel)
    if name == "copilot":
        return first_of_next_month_utc(now_f), "fallback-1st"
    return now_f + fuel_cooldown_seconds(name), "fixed-7d"


def _fuel_name(fuel: str) -> str:
    return (fuel or "copilot").strip().lower() or "copilot"


def _fuel_block(doc: dict, fuel: str) -> dict:
    fuels = doc.get("fuels")
    if not isinstance(fuels, dict):
        return {}
    block = fuels.get(_fuel_name(fuel))
    return block if isinstance(block, dict) else {}


def fuel_exhausted_until(home: Path, fuel: str = "copilot") -> float | None:
    """FR #5397: per-fuel exhausted_until; Copilot still reads the legacy top-level key."""
    doc = load_allowance(home)
    until = _num(_fuel_block(doc, fuel).get("exhausted_until"))
    if until is not None:
        return until
    if _fuel_name(fuel) == "copilot":
        return _num(doc.get("exhausted_until"))
    return None


def cooldown_active(home: Path, *, now: float | None = None, fuel: str = "copilot") -> bool:
    now_f = time.time() if now is None else float(now)
    until = fuel_exhausted_until(home, fuel)
    return until is not None and now_f < until


def has_allowance(home: Path, *, now: float | None = None) -> bool:
    """Live cache / last read. No cache means off (do not steal IRC jobs). Unknown means off (FR #5174 fail closed)."""
    if cooldown_active(home, now=now):
        return False
    doc = load_allowance(home)
    if not doc:
        return False
    if (
        doc.get("remaining") is None
        and not doc.get("state")
        and not doc.get("unlimited")
        and not doc.get("exhausted")
        and not doc.get("tasks_exhausted")
    ):
        return False
    return allowance_from_pool(doc)


def refresh_allowance(
    home: Path,
    *,
    fetch_user: Callable[[], dict] | None = None,
    now: float | None = None,
) -> dict:
    """Read GET /copilot_internal/user (5 min cache). Parse failure -> unknown."""
    now_f = time.time() if now is None else float(now)
    if cooldown_active(home, now=now_f):
        return load_allowance(home)
    doc = load_allowance(home)
    fetched = _num(doc.get("fetched_epoch"))
    if fetched is not None and (now_f - fetched) < CACHE_S and doc.get("state"):
        return doc
    if fetch_user is None:
        pool = dict(parse_user_quota(None))
        pool["state"] = "unknown"
        pool["fetched_at"] = ""
        pool["fetched_epoch"] = now_f
        Path(home).mkdir(parents=True, exist_ok=True)
        merged = dict(doc)
        merged.update(pool)
        _allow_path(home).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        return merged
    try:
        raw = fetch_user()
        pool = parse_user_quota(raw if isinstance(raw, dict) else None)
    except Exception as exc:  # noqa: BLE001
        log.warning("copilot_internal/user failed: %s", type(exc).__name__)
        pool = parse_user_quota(None)
    pool["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_f))
    pool["fetched_epoch"] = now_f
    if pool.get("state") == "ok":
        pool["tasks_exhausted"] = False
        pool["exhausted"] = False
        pool.pop("exhausted_until", None)
        pool.pop("exhausted_until_utc", None)
        pool.pop("pause_announced_until", None)
    Path(home).mkdir(parents=True, exist_ok=True)
    merged = dict(doc)
    merged.update(pool)
    _allow_path(home).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    if merged.get("state") == "exhausted":
        mark_tokens_exhausted(home, now=now_f, reset_date=merged.get("reset_at"))
        return load_allowance(home)
    return merged


def pool_for_digest(home: Path) -> dict:
    doc = load_allowance(home)
    return {
        "plan": doc.get("plan") or "",
        "used": doc.get("used"),
        "remaining": doc.get("remaining"),
        "unlimited": bool(doc.get("unlimited")),
        "percent_remaining": doc.get("percent_remaining"),
        "reset_at": doc.get("reset_at") or "",
        "source": doc.get("source") or "copilot_internal/user",
        "fetched_at": doc.get("fetched_at") or "",
        "state": doc.get("state") or "unknown",
        "resume_at": doc.get("exhausted_until_utc") or "",
        "resume_source": doc.get("exhausted_until_source") or "",
    }


def is_exhausted(resp: dict | None) -> bool:
    if not isinstance(resp, dict):
        return False
    status = int(resp.get("status") or resp.get("status_code") or 0)
    msg = str(resp.get("message") or resp.get("error") or "").lower()
    if status in (402, 403, 429) and any(
        k in msg for k in ("quota", "allowance", "rate", "exhaust", "copilot")
    ):
        return True
    if "allowance exhausted" in msg or "quota exceeded" in msg:
        return True
    if "out of tokens" in msg or "no tokens" in msg or "token quota" in msg:
        return True
    return False


def _utc_iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def release_held_copilot_rows(home: Path) -> int:
    """Return Copilot-accepted rows to unaccepted for other fuel (no giveup_seats)."""
    n = 0
    try:
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            acc = doc.get("accepted") or []
            keep = []
            un = doc.setdefault("unaccepted", [])
            for r in acc:
                if str(r.get("nick") or "").strip().lower() == COPILOT_NICK:
                    moved = dict(r)
                    moved.pop("nick", None)
                    moved.pop("accepted_ts", None)
                    if not any(
                        str(u.get("repo")) == str(moved.get("repo"))
                        and str(u.get("id")) == str(moved.get("id"))
                        and str(u.get("task") or "").upper()
                        == str(moved.get("task") or "").upper()
                        for u in un
                    ):
                        un.append(moved)
                    n += 1
                else:
                    keep.append(r)
            doc["accepted"] = keep
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
    except (TimeoutError, OSError, ValueError):
        return n
    return n


def mark_tokens_exhausted(
    home: Path,
    *,
    fuel: str = "copilot",
    now: float | None = None,
    announce: Callable[[str], None] | None = None,
    reset_date: object = None,
) -> dict[str, Any]:
    """FR #5316 / #5397 / #5433 / #5515: persist per-fuel cooldown; keep an active until."""
    now_f = time.time() if now is None else float(now)
    name = _fuel_name(fuel)
    doc = load_allowance(home)
    already = fuel_exhausted_until(home, name)
    # FR #5433: do not extend or re-announce while the current until is still active.
    if already and now_f < already:
        until = already
        source = str(doc.get("exhausted_until_source") or _fuel_block(doc, name).get("exhausted_until_source") or "")
        if not source:
            source = "api" if parse_quota_reset_epoch(reset_date) is not None else (
                "fallback-1st" if name == "copilot" else "fixed-7d"
            )
    else:
        raw = reset_date
        if raw is None:
            raw = doc.get("reset_at") or doc.get("quota_reset_date") or doc.get("quota_reset_date_utc")
        until, source = quota_pause_until(now_f, reset_date=raw, fuel=name)
    fuels = doc.get("fuels")
    if not isinstance(fuels, dict):
        fuels = {}
    block = dict(fuels.get(name) or {}) if isinstance(fuels.get(name), dict) else {}
    block["exhausted_until"] = until
    block["exhausted_until_utc"] = _utc_iso(until)
    block["exhausted_until_source"] = source
    fuels[name] = block
    doc["fuels"] = fuels
    doc["fuel"] = name
    if name == "copilot":
        doc["tasks_exhausted"] = True
        doc["exhausted"] = True
        doc["state"] = "exhausted"
        doc["exhausted_until"] = until
        doc["exhausted_until_utc"] = _utc_iso(until)
        doc["exhausted_until_source"] = source
    Path(home).mkdir(parents=True, exist_ok=True)
    released = 0
    if name == "copilot":
        released = release_held_copilot_rows(home)
    until_utc = _utc_iso(until)
    line = f"{name} out of tokens - paused until {until_utc} ({source})"
    announced = doc.get("pause_announced_until")
    if announced != until:
        doc["pause_announced_until"] = until
        if announce:
            announce(line)
        else:
            with contextlib.suppress(Exception):
                bobreport.enqueue_chair_fleet_privmsg(home, line)
    _allow_path(home).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return {"exhausted_until": until, "released": released, "line": line, "source": source}


def record_api_result(
    home: Path,
    resp: dict | None,
    *,
    now: float | None = None,
    announce: Callable[[str], None] | None = None,
) -> None:
    if is_exhausted(resp):
        mark_tokens_exhausted(home, now=now, announce=announce)
        return
    if isinstance(resp, dict) and int(resp.get("status") or 0) in (200, 201, 202):
        doc = load_allowance(home)
        rem = doc.get("remaining")
        if rem is not None:
            try:
                set_allowance(home, remaining=max(0, int(rem) - 1), exhausted=False)
            except (TypeError, ValueError):
                set_allowance(home, exhausted=False)
        else:
            set_allowance(home, exhausted=False)


def build_task_body(row: dict) -> dict:
    task = str(row.get("task") or "FR").upper()
    repo = str(row.get("repo") or "")
    ident = str(row.get("id") or "")
    url = str(row.get("url") or "")
    title = str(row.get("title") or "")
    prompt_lines = [
        f"You are the bobiverse {task} worker (virtual seat nick=copilot).",
        f"Repo: {repo}  Job: {task} {ident}  {url}",
        title,
        "Follow the repo AGENTS.md / CAST IRON rules. Never merge.",
        "Never print secrets.",
    ]
    if task == "MRB":
        prompt_lines.extend(
            [
                "Hostile tests-first review. Post a machine-parseable PR comment whose",
                "first line is exactly MRB PASS or MRB FAIL, then a ## MRB board with",
                "**Verdict:** PASS|FAIL and the head SHA.",
                "Do not MRB a PR you authored (self-MRB).",
            ]
        )
    else:
        prompt_lines.append(
            "Implement the issue. Open one PR whose body contains "
            f"Closes {repo}{ident if ident.startswith('#') else '#' + ident}."
        )
    return {"prompt": "\n".join(prompt_lines)}


def should_dispatch(row: dict, *, allowance: bool, now: float | None = None) -> bool:
    if not allowance:
        return False
    # FR #5267: a give-up release is never offered back to Copilot.
    if gitclaim.nick_in_giveup_seats(row, COPILOT_NICK):
        return False
    task = str(row.get("task") or "").upper()
    if task not in ("FR", "FIX", "MRB"):
        return False
    if gitclaim.row_needs_human(row):
        return False
    live = {COPILOT_NICK}
    if gitclaim.row_gave_up_by(row, COPILOT_NICK, live=live):
        return False
    now_f = time.time() if now is None else float(now)
    if gitclaim.row_on_cooldown(row, now_f, COPILOT_NICK, live=live):
        return False
    labels = row.get("labels") or []
    if isinstance(labels, str):
        labels = [labels]
    title = str(row.get("title") or "").strip() or str(row.get("line") or "").strip()
    if task in ("FR", "FIX") and gitclaim.fr_hold_reason(
        title=title, body=str(row.get("body") or ""), labels=labels
    ):
        return False
    if task == "MRB" and gitclaim.pr_hold_reason(
        title=title, body=str(row.get("body") or ""), labels=labels
    ):
        return False
    # FR #5174: machine-pinned rows stay on IRC seats (never Copilot).
    row_eff = dict(row) if isinstance(row, dict) else {}
    with contextlib.suppress(Exception):
        gitclaim._stamp_require_machine(row_eff)
    req = str(row_eff.get("require_machine") or "").strip()
    if req and req.lower() not in ("*", "any", "none", "-", ""):
        return False
    if task == "MRB":
        authors = {a.lower() for a in gitclaim.row_author_seats(row)}
        if COPILOT_NICK in authors:
            return False
        if gitclaim.review_blocked_for_author(row, COPILOT_NICK, live={COPILOT_NICK}):
            return False
    return True


def is_high_priority(home: Path, row: dict) -> bool:
    """Use Jeeves' focus ordering; only an explicit high-ranked focus is eligible."""
    import focus_ignore

    if not focus_ignore.is_high_priority_repo(str(row.get("repo") or "")):
        return False
    key = focus_ignore.offer_sort_key(home, row)
    return len(key) > 1 and key[1] == focus_ignore.NAMED_PRIORITY["high"]


def parse_mrb_verdict(body: str) -> str | None:
    first = (body or "").lstrip().splitlines()[:8]
    blob = "\n".join(first).upper()
    if "MRB PASS" in blob or "**VERDICT:** PASS" in blob:
        if "MRB FAIL" in blob.split("MRB PASS")[0]:
            return "FAIL"
        return "PASS"
    if "MRB FAIL" in blob or "**VERDICT:** FAIL" in blob:
        return "FAIL"
    return None


def announce_handoff(*, repo: str, task: str, ident: str, task_url: str) -> str:
    ident_s = ident if str(ident).startswith("#") else f"#{ident}"
    return (
        f"{COPILOT_NICK}: {task} {repo}{ident_s} {task_url} "
        f"(Copilot Coding Agent hand-off)"
    )


def announce_complete(
    *,
    repo: str,
    task: str,
    ident: str,
    result: str,
    pr_url: str = "",
    reason: str = "",
) -> str:
    ident_s = ident if str(ident).startswith("#") else f"#{ident}"
    res = (result or reason or "done").strip()
    if str(task).upper() == "MRB" and res.upper() in ("PASS", "FAIL"):
        return f"{COPILOT_NICK}: DONE MRB {repo}{ident_s} {res.upper()} {pr_url}".rstrip()
    if reason:
        return f"DONE {task} {repo}{ident_s} copilot {reason} {pr_url}".rstrip()
    return f"DONE {task} {repo}{ident_s} {pr_url}".rstrip()


def _load_jobs(home: Path) -> dict:
    p = _jobs_path(home)
    if not p.is_file():
        return {"jobs": []}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"jobs": []}
    if not isinstance(doc, dict):
        return {"jobs": []}
    doc.setdefault("jobs", [])
    return doc


def _save_jobs(home: Path, doc: dict) -> None:
    Path(home).mkdir(parents=True, exist_ok=True)
    _jobs_path(home).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def dispatch_row(
    home: Path,
    row: dict,
    *,
    post: Callable[[str, dict], dict] | None = None,
    now: float | None = None,
    announce: Callable[[str], None] | None = None,
) -> dict:
    if not has_allowance(home, now=now):
        return {"status": "exhausted"}
    if not is_high_priority(home, row):
        return {"status": "skip"}
    if not should_dispatch(row, allowance=True, now=now):
        return {"status": "skip"}
    body = build_task_body(row)
    path = tasks_api_path(str(row.get("repo") or ""))
    # FR #5174: never mark taken / announce without a real tasks POST + task id.
    if post is None:
        return {"status": "no-post"}
    try:
        resp = post(path, body) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("copilot tasks POST failed: %s", type(exc).__name__)
        return {"status": "send-failed", "error": type(exc).__name__}
    if not isinstance(resp, dict):
        resp = {}
    record_api_result(home, resp, now=now, announce=announce)
    if is_exhausted(resp):
        return {"status": "exhausted"}
    status = int(resp.get("status") or resp.get("status_code") or 0)
    if status and status >= 400:
        return {"status": "error", "response": resp}
    task_id = str(resp.get("id") or resp.get("task_id") or "")
    task_url = str(resp.get("html_url") or resp.get("url") or "")
    if not task_id:
        return {"status": "error", "response": resp, "reason": "missing-task-id"}
    ident = str(row.get("id") or "")
    repo = str(row.get("repo") or "")
    task = str(row.get("task") or "FR").upper()
    st, _job = shop_listen.accept_job_by_ref(
        home,
        nick=COPILOT_NICK,
        channel="#bobiverse",
        repo=repo,
        task=task,
        ident=ident,
        title=str(row.get("title") or ""),
    )
    if st not in ("ok", "duplicate"):
        return {"status": "accept-failed", "accept": st}
    doc = _load_jobs(home)
    doc["jobs"].append(
        {
            "repo": repo,
            "task": task,
            "id": ident,
            "task_id": task_id,
            "task_url": task_url,
            "started": float(now if now is not None else time.time()),
        }
    )
    _save_jobs(home, doc)
    line = announce_handoff(repo=repo, task=task, ident=ident, task_url=task_url or path)
    if announce:
        announce(line)
    else:
        bobreport.enqueue_chair_fleet_privmsg(home, line)
        mid = ""
        try:
            mid = (bobreport.machine_id() or "").strip()
        except Exception:  # noqa: BLE001
            mid = ""
        if mid:
            bobreport.enqueue_chair_fleet_privmsg(home, line, channel=f"#{mid}")
    return {"status": "dispatched", "task_url": task_url, "line": line}


def _explicitly_off(val: object) -> bool:
    if val is False or val == 0:
        return True
    return isinstance(val, str) and val.strip().lower() in ("0", "false", "no", "off")


def dispatch_enabled(home: Path) -> bool:
    """False when Copilot dispatch is off (FR #5267).

    Off when ``copilot-allowance.json`` is absent, or when that file (or its
    ``copilot`` block) sets ``enabled`` false. An explicit ``BOB_FUEL_COPILOT``
    off-value from FR #5317 counts too; an unset variable does not, so a
    present allowance file still drives dispatch.
    """
    if not _allow_path(home).is_file():
        return False
    doc = load_allowance(home)
    if _explicitly_off(doc.get("enabled")):
        return False
    cop = doc.get("copilot")
    if isinstance(cop, dict) and _explicitly_off(cop.get("enabled")):
        return False
    raw = os.environ.get("BOB_FUEL_COPILOT")
    if raw is not None and str(raw).strip():
        try:
            import fuel_chain

            if not fuel_chain.stage_enabled("copilot"):
                return False
        except Exception:  # noqa: BLE001
            if _explicitly_off(raw):
                return False
    return True


def _is_copilot_row(row: dict) -> bool:
    return str(row.get("nick") or "").strip().lower() == COPILOT_NICK


def _done_blocks_requeue(doc: dict, repo: str, task: str, ident: str) -> bool:
    for r in doc.get("done") or []:
        if not isinstance(r, dict):
            continue
        if not gitclaim._same(r, repo, task, ident):
            continue
        if str(r.get("result") or "").upper() in ("CLOSED", "MERGED", "COPILOT_PR"):
            return True
    return False


def _forget_job(home: Path, repo: str, task: str, ident: str) -> None:
    jobs = _load_jobs(home)
    kept = []
    for job in jobs.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        if (
            gitclaim._repo_key(job.get("repo")) == gitclaim._repo_key(repo)
            and str(job.get("task") or "").upper() == str(task or "").upper()
            and gitclaim._norm_row_id(job.get("id")) == gitclaim._norm_row_id(ident)
        ):
            continue
        kept.append(job)
    if len(kept) != len(jobs.get("jobs") or []):
        jobs["jobs"] = kept
        _save_jobs(home, jobs)


def _matching_job(home: Path, row: dict) -> dict | None:
    repo = str(row.get("repo") or "")
    task = str(row.get("task") or "").upper()
    ident = gitclaim._norm_row_id(row.get("id"))
    for job in _load_jobs(home).get("jobs") or []:
        if not isinstance(job, dict):
            continue
        if (
            gitclaim._repo_key(job.get("repo")) == gitclaim._repo_key(repo)
            and str(job.get("task") or "").upper() == task
            and gitclaim._norm_row_id(job.get("id")) == ident
        ):
            return job
    return None


def _job_is_live(job: dict | None, now: float) -> bool:
    if not isinstance(job, dict):
        return False
    if str(job.get("state") or "").strip().lower() in (
        "completed",
        "complete",
        "failed",
        "done",
        "cancelled",
        "canceled",
        "error",
    ):
        return False
    try:
        started = float(job.get("started") or 0)
    except (TypeError, ValueError):
        started = 0.0
    if not started:
        return False
    return (float(now) - started) < TASK_TIMEOUT_S


def _pull_url(repo: str, raw: str) -> str:
    text = str(raw or "").strip()
    if "/pull/" in text:
        return text
    num = text.lstrip("#")
    if num.isdigit() and repo:
        return f"https://github.com/{repo}/pull/{num}"
    return ""


def _job_pr_url(job: dict | None, repo: str) -> str:
    if not isinstance(job, dict):
        return ""
    if str(job.get("pr_state") or "").strip().lower() == "closed":
        return ""
    for key in ("pr_url", "pull_url", "html_url"):
        url = _pull_url(repo, str(job.get(key) or ""))
        if "/pull/" in url:
            return url
    for key in ("pr", "pr_id", "pull", "pull_number"):
        url = _pull_url(repo, str(job.get(key) or ""))
        if url:
            return url
    return ""


def _sibling_copilot_pr(doc: dict, row: dict) -> str:
    """Open Copilot MRB that references this issue (PR webhook tracker)."""
    repo = str(row.get("repo") or "")
    ident = gitclaim._norm_row_id(row.get("id"))
    key = gitclaim.fr_issue_key(repo, ident)
    for bucket in ("unaccepted", "accepted"):
        for other in doc.get(bucket) or []:
            if not isinstance(other, dict) or other is row:
                continue
            if str(other.get("task") or "").upper() != "MRB":
                continue
            if gitclaim._repo_key(other.get("repo")) != gitclaim._repo_key(repo):
                continue
            if str(other.get("state") or "").strip().lower() == "closed":
                continue
            author = " ".join(
                str(other.get(k) or "")
                for k in ("author_seat", "author", "opened_by", "nick", "implementer_seat")
            ).lower()
            if "copilot" not in author:
                continue
            refs = [gitclaim._norm_row_id(x) for x in gitclaim._row_refs(other)]
            sup = str(other.get("supersedes") or "")
            if ident not in refs and sup != key and ident not in sup:
                continue
            url = _pull_url(repo, str(other.get("url") or "")) or _pull_url(
                repo, str(other.get("id") or "")
            )
            if url:
                return url
    return ""


def _live_copilot_pr_url(doc: dict, row: dict, job: dict | None) -> str:
    """URL of a live Copilot PR for this row, or empty."""
    repo = str(row.get("repo") or "")
    task = str(row.get("task") or "").upper()
    from_job = _job_pr_url(job, repo)
    if from_job:
        return from_job
    if task == "FR":
        return _sibling_copilot_pr(doc, row)
    if task in ("MRB", "PR") and str(row.get("state") or "").strip().lower() != "closed":
        return _pull_url(repo, str(row.get("url") or "")) or _pull_url(
            repo, str(row.get("id") or "")
        )
    return ""


def _ids_for_repo(mapping: dict | None, repo: str) -> set[str]:
    if not isinstance(mapping, dict):
        return set()
    key = gitclaim._repo_key(repo)
    found = None
    for name, nums in mapping.items():
        if gitclaim._repo_key(name) == key:
            found = nums
            break
    if not found:
        return set()
    return {gitclaim._norm_row_id(n) for n in found}


def _repo_was_fetched(repo: str, fetched: set | None) -> bool:
    if not fetched:
        return False
    key = gitclaim._repo_key(repo)
    return any(gitclaim._repo_key(r) == key for r in fetched)


def _row_is_terminal(
    row: dict,
    *,
    open_issues: dict | None,
    open_pulls: dict | None,
    fetched_repos: set | None,
) -> bool:
    """Closed issue/PR, or cancel already delivered (FR #5267)."""
    if row.get("cancel_pending") and row.get("cancel_notified"):
        return True
    if str(row.get("state") or "").strip().lower() == "closed":
        return True
    if row.get("merged") in (True, "true", "1", 1):
        return True
    repo = str(row.get("repo") or "")
    if not _repo_was_fetched(repo, fetched_repos):
        return False
    task = str(row.get("task") or "").upper()
    ident = gitclaim._norm_row_id(row.get("id"))
    if task in ("FR", "PR") and open_issues is not None:
        return ident not in _ids_for_repo(open_issues, repo)
    if task == "MRB" and open_pulls is not None:
        return ident not in _ids_for_repo(open_pulls, repo)
    return False


def _idle_holder(home: Path | None, row: dict) -> None:
    if home is None:
        return
    seat = gitclaim._seat_holder_nick(row)
    if not seat:
        return
    ident = str(row.get("id") or "").lstrip("#")
    with contextlib.suppress(Exception):
        bobreport.clear_seat_doing(home, seat, only_if_work_contains=ident or "x")


def _to_done(row: dict, *, result: str, url: str = "") -> dict:
    fin = dict(row)
    holder = gitclaim._seat_holder_nick(row)
    fin["result"] = result
    fin["done_ts"] = gitclaim._utc_now()
    if holder:
        fin["done_by"] = holder
    if url:
        fin["url"] = url
    if result in ("CLOSED", "MERGED"):
        fin["state"] = "closed"
        if result == "MERGED":
            fin["merged"] = True
    for k in (
        "nick",
        "accepted_ts",
        "accepted_by",
        "offered_to",
        "offered_ts",
        "offered_channel",
        "cancel_pending",
    ):
        fin.pop(k, None)
    return fin


def _stamp_copilot_giveup(row: dict, *, now: float) -> None:
    seats = [s.strip() for s in str(row.get("giveup_seats") or "").split(",") if s.strip()]
    if COPILOT_NICK not in {s.lower() for s in seats}:
        seats.append(COPILOT_NICK)
    row["giveup_seats"] = ",".join(seats)
    try:
        row["giveup_count"] = int(row.get("giveup_count") or 0) + 1
    except (TypeError, ValueError):
        row["giveup_count"] = 1
    row["giveup_ts"] = gitclaim._utc_now()
    row["cooldown_until"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(float(now) + float(gitclaim.GIVEUP_COOLDOWN_S)),
    )


def _giveup_release(doc: dict, row: dict, *, now: float) -> str:
    """Move a copilot hold back to unaccepted with give-up cooldown.

    Returns ``released`` when appended, ``deduped`` when the seat queue
    already has the row (stamp that copy; do not add a second one).
    """
    repo = str(row.get("repo") or "")
    task = str(row.get("task") or "").upper()
    ident = str(row.get("id") or "")
    un = doc.setdefault("unaccepted", [])
    for existing in un:
        if isinstance(existing, dict) and gitclaim._same(existing, repo, task, ident):
            _stamp_copilot_giveup(existing, now=now)
            return "deduped"
    moved = dict(row)
    _stamp_copilot_giveup(moved, now=now)
    moved.pop("nick", None)
    moved.pop("accepted_ts", None)
    moved.pop("accepted_by", None)
    un.append(moved)
    return "released"


def _append_done(doc: dict, fin: dict) -> None:
    done = doc.setdefault("done", [])
    done.append(fin)
    cap = int(getattr(gitclaim, "DONE_CAP", 100) or 100)
    if len(done) > cap:
        doc["done"] = done[-cap:]


def settle_stuck_accepted_unlocked(
    home: Path,
    doc: dict,
    *,
    now: float | None = None,
    open_issues: dict | None = None,
    open_pulls: dict | None = None,
    fetched_repos: set | None = None,
) -> dict:
    """Drop terminal accepts and release stranded nick=copilot rows (FR #5267).

    Mutates ``doc`` and forgets matching copilot jobs. Does not take the queue
    lock and does not write ``queue.json`` (the caller holds the lock).
    """
    now_f = time.time() if now is None else float(now)
    enabled = dispatch_enabled(home)
    dropped = 0
    released = 0
    kept: list[dict] = []
    for row in doc.get("accepted") or []:
        if not isinstance(row, dict):
            continue
        repo = str(row.get("repo") or "")
        task = str(row.get("task") or "").upper()
        ident = str(row.get("id") or "")
        if _row_is_terminal(
            row,
            open_issues=open_issues,
            open_pulls=open_pulls,
            fetched_repos=fetched_repos,
        ):
            result = "MERGED" if row.get("merged") in (True, "true", "1", 1) else "CLOSED"
            _append_done(doc, _to_done(row, result=result))
            _idle_holder(home, row)
            _forget_job(home, repo, task, ident)
            dropped += 1
            continue
        if not _is_copilot_row(row):
            kept.append(row)
            continue
        job = _matching_job(home, row)
        pr_url = _live_copilot_pr_url(doc, row, job)
        if pr_url and task == "FR":
            # The open PR (webhook MRB) tracks the work. Do not re-offer the issue.
            _append_done(doc, _to_done(row, result="COPILOT_PR", url=pr_url))
            _idle_holder(home, row)
            _forget_job(home, repo, task, ident)
            dropped += 1
            continue
        if pr_url and task in ("MRB", "PR"):
            # Already tracked via the PR webhook row, or this hold is that PR.
            # Never keep a second copy.
            _giveup_release(doc, row, now=now_f)
            _idle_holder(home, row)
            _forget_job(home, repo, task, ident)
            released += 1
            continue
        # FR #5201: a tracked job (even past TASK_TIMEOUT_S) stays accepted so
        # handle_timeout_or_fail can keep artifact work or apply seat give-up.
        if job is not None:
            kept.append(row)
            continue
        if enabled and _job_is_live(job, now_f):
            kept.append(row)
            continue
        _giveup_release(doc, row, now=now_f)
        _idle_holder(home, row)
        _forget_job(home, repo, task, ident)
        released += 1
    doc["accepted"] = kept
    return {"dropped": dropped, "released": released}


def settle_stuck_accepted(
    home: Path,
    *,
    now: float | None = None,
    open_issues: dict | None = None,
    open_pulls: dict | None = None,
    fetched_repos: set | None = None,
) -> dict:
    """Lock, settle, and persist. Safe to call from the chair tick."""
    now_f = time.time() if now is None else float(now)
    try:
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            stats = settle_stuck_accepted_unlocked(
                home,
                doc,
                now=now_f,
                open_issues=open_issues,
                open_pulls=open_pulls,
                fetched_repos=fetched_repos,
            )
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
            return stats
    except (TimeoutError, OSError, ValueError):
        return {"dropped": 0, "released": 0}


def _existing_work(job: dict, task_info: dict, get: Callable[[str], Any]) -> bool:
    """Check task output and GitHub before returning a cloud job to local seats."""
    repo = str(job["repo"])
    num = str(job["id"]).lstrip("#")
    task = str(job["task"]).lower()

    if task == "mrb":
        return False  # The PR being reviewed is input, not Copilot's output.
    task_pulls: set[str] = set()
    task_branches: set[str] = set()
    artifacts = [task_info] + [
        s for s in task_info.get("sessions") or [] if isinstance(s, dict)
    ]
    for info in artifacts:
        for key in ("pull_request", "pull_request_url", "pull_requests"):
            values = info.get(key) or []
            if not isinstance(values, list):
                values = [values]
            for value in values:
                url = (
                    value.get("html_url") or value.get("url")
                    if isinstance(value, dict) else value
                )
                parsed = gitclaim.parse_github_pull_url(str(url or ""))
                if parsed and parsed[0].lower() == repo.lower():
                    task_pulls.add(parsed[1])
                elif not parsed and isinstance(value, dict) and value.get("number"):
                    task_pulls.add(f"#{value['number']}")
        for key in ("branch", "branch_name", "head_ref"):
            branch = info.get(key)
            if isinstance(branch, dict):
                branch = branch.get("ref") or branch.get("name")
            if isinstance(branch, str) and branch:
                task_branches.add(branch.removeprefix("refs/heads/"))
    page = 1
    while True:
        pulls = get(f"repos/{repo}/pulls?state=open&per_page=100&page={page}")
        if not isinstance(pulls, list):
            raise ValueError("invalid pulls response")
        for pr in pulls:
            if f"#{pr.get('number')}" in task_pulls:
                return True
            login = str((pr.get("user") or {}).get("login") or "").lower()
            branch = str((pr.get("head") or {}).get("ref") or "")
            if "copilot" not in login and not branch.startswith("copilot/"):
                continue
            refs = gitclaim.extract_closes_issue_ids(str(pr.get("body") or ""), repo=repo)
            if f"#{num}" in refs or re.match(rf"copilot/{task}-{re.escape(num)}(?:-|$)", branch):
                return True
        if len(pulls) < 100:
            break
        page += 1
    for branch in sorted(task_branches):
        branches = get(f"repos/{repo}/git/matching-refs/heads/{quote(branch, safe='/')}")
        if not isinstance(branches, list):
            raise ValueError("invalid refs response")
        if any(b.get("ref") == f"refs/heads/{branch}" for b in branches):
            return True
    branches = get(f"repos/{repo}/git/matching-refs/heads/copilot/{task}-{num}")
    if not isinstance(branches, list):
        raise ValueError("invalid refs response")
    return any(
        re.match(rf"refs/heads/copilot/{task}-{re.escape(num)}(?:-|$)", str(b.get("ref") or ""))
        for b in branches
    )


def handle_timeout_or_fail(
    home: Path, job: dict, *, now: float, reason: str = "timeout",
    get: Callable[[str], Any] | None = None,
) -> dict:
    """Keep cloud work tracked, otherwise use the same GIVEUP path as IRC seats."""
    repo = str(job.get("repo") or "")
    task = str(job.get("task") or "FR").upper()
    ident = str(job.get("id") or "")
    accepted = next((
        r for r in gitclaim.load_accepted(home)
        if (r.get("repo"), str(r.get("task") or "").upper(), r.get("id"), r.get("nick"))
        == (repo, task, ident, COPILOT_NICK)
    ), None)
    if accepted is not None:
        info = {}
        try:
            if get is not None:
                info = get(f"{tasks_api_path(repo)}/{job['task_id']}")
                if not isinstance(info, dict):
                    raise ValueError("invalid task response")
                state = str(info.get("state") or info.get("status") or "").lower()
                if state in ("failed", "cancelled", "canceled", "error"):
                    reason = state
            started = float(job.get("started") or 0)
            if reason == "timeout" and now - started < TASK_TIMEOUT_S:
                return {"status": "pending"}
            if get is not None and _existing_work(job, info, get):
                jobs = _load_jobs(home)
                for tracked in jobs.get("jobs") or []:
                    if tracked.get("task_id") == job.get("task_id"):
                        tracked["started"] = now
                _save_jobs(home, jobs)
                return {"status": "tracking"}
        except Exception as exc:  # noqa: BLE001
            log.warning("copilot work check failed: %s", type(exc).__name__)
            return {"status": "pending"}
        repeated = gitclaim.row_gave_up_by(accepted, COPILOT_NICK) or bool(
            gitclaim.ledger_blocks(gitclaim.ledger_load(home), accepted, COPILOT_NICK)
        )
        status, moved = shop_listen.return_job_to_unaccepted(
            home, repo=repo, task=task, ident=ident, now=now, reason=f"copilot {reason}",
            expected_nick=COPILOT_NICK,
        )
        if status != "ok":
            return {"status": "error"}
        gitclaim.ledger_note_event(home, COPILOT_NICK, "GIVEUP", task, repo, ident, job=moved)
        with contextlib.suppress(Exception):
            gitclaim.ledger_giveup(home, COPILOT_NICK, repo, task, ident)
        if moved is not None:
            try:
                if int(moved.get("giveup_count") or 0) >= 2:
                    repeated = True
            except (TypeError, ValueError):
                pass
        if repeated:
            import stall_detectors
            import stall_filer

            findings = stall_detectors.detect_all(
                {"live": {COPILOT_NICK}, "unaccepted": [moved]}
            )
            for f in findings:
                if isinstance(f, dict) and not f.get("fingerprint"):
                    f["fingerprint"] = str(f.get("title") or f.get("id") or "copilot-timeout")
            actions = stall_filer.apply_findings(
                findings,
                home=home, now=now, excerpt=f"Repeated Copilot {reason}",
                create=stall_filer.default_create,
            )
            if not actions:
                title = f"stall:all-gave-up:{repo}{ident if str(ident).startswith('#') else '#' + ident}"
                stall_filer.default_create(title, f"Repeated Copilot {reason}")
    jobs = _load_jobs(home)
    jobs["jobs"] = [
        j
        for j in jobs.get("jobs") or []
        if not (j.get("repo") == repo and j.get("id") == ident and j.get("task") == task)
    ]
    _save_jobs(home, jobs)
    if accepted is None:
        return {"status": "stale"}
    with contextlib.suppress(Exception):
        gitclaim.ledger_giveup(home, COPILOT_NICK, repo, task, ident)
    line = announce_complete(
        repo=repo, task=task, ident=ident, result="fail", reason=reason
    )
    bobreport.enqueue_chair_fleet_privmsg(home, line)
    return {"status": "giveup", "reason": reason}



def handle_issue_comment(home: Path, payload: dict) -> dict | None:
    comment = payload.get("comment") if isinstance(payload.get("comment"), dict) else {}
    user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    login = str(user.get("login") or "").lower()
    if "copilot" not in login:
        return None
    body = str(comment.get("body") or "")
    verdict = parse_mrb_verdict(body)
    issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
    if not issue.get("pull_request") and not verdict:
        return None
    num = issue.get("number")
    if num is None:
        return None
    ident = f"#{int(num)}"
    repo = ""
    repo_blob = payload.get("repository")
    if isinstance(repo_blob, dict):
        repo = str(repo_blob.get("full_name") or "")
    pr_url = str(issue.get("html_url") or "")
    if "/issues/" in pr_url and issue.get("pull_request"):
        pr_url = pr_url.replace("/issues/", "/pull/")
    if verdict:
        st, job = shop_listen.complete_job_by_ref(
            home,
            nick=COPILOT_NICK,
            repo=repo,
            task="MRB",
            ident=ident,
            result=verdict,
            url=pr_url,
        )
        line = announce_complete(
            repo=repo, task="MRB", ident=ident, result=verdict, pr_url=pr_url
        )
        bobreport.enqueue_chair_fleet_privmsg(home, line)
        return {"status": st, "verdict": verdict, "line": line}
    return None


def stamp_webhook_activity(home: Path, event: str, payload: dict) -> None:
    """Mark matching queue rows so review/check/workflow do not need !resync."""
    ev = (event or "").strip().lower()
    if ev not in ("pull_request_review", "check_run", "workflow_run", "check_suite"):
        return
    repo_blob = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    repo = str(repo_blob.get("full_name") or "")
    num = None
    pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
    if pr.get("number") is not None:
        num = pr.get("number")
    if num is None:
        return
    ident = f"#{int(num)}"
    try:
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            changed = False
            for bucket in ("unaccepted", "accepted"):
                for r in doc.get(bucket) or []:
                    if str(r.get("repo")) == repo and str(r.get("id")) == ident:
                        r["last_webhook_event"] = ev
                        r["last_webhook_ts"] = gitclaim._utc_now()
                        changed = True
            if changed:
                gitclaim._write_queue(gitclaim.queue_path(home), doc)
    except (TimeoutError, OSError, ValueError):
        return


def resync_is_fallback(reason: str) -> bool:
    return str(reason or "").strip().lower() in FALLBACK_REASONS


def file_webhook_stall(home: Path, *, repo: str, kind: str = "webhook-ensure", error: str = "") -> None:
    """FR #5164: permission / API failure on webhook ensure is a stall, not silent."""
    try:
        import stall_filer

        stall_filer.apply_findings(
            [
                {
                    "id": "webhook-ensure",
                    "key": repo,
                    "fingerprint": f"webhook-ensure:{repo}:{kind}",
                    "title": f"Jeeves cannot ensure git webhook on {repo}",
                    "evidence": {"repo": repo, "kind": kind, "error": error},
                }
            ],
            home=home,
            excerpt=error,
        )
    except Exception:  # noqa: BLE001
        log.warning("stall-file webhook-ensure failed repo=%s", repo)


def ensure_repo_webhook(
    repo: str,
    *,
    list_hooks: Callable[[str], list],
    create: Callable[[dict], Any],
    patch: Callable[..., Any],
    file_stall: Callable[..., Any] | None = None,
) -> dict:
    try:
        hooks = list(list_hooks(repo) or [])
    except Exception as exc:  # noqa: BLE001
        info = {"action": "stall", "repo": repo, "error": str(exc)}
        if file_stall:
            file_stall(repo=repo, kind="webhook-ensure", error=str(exc))
        return info
    want = set(REQUIRED_HOOK_EVENTS)
    match = None
    for h in hooks:
        if not isinstance(h, dict):
            continue
        cfg = h.get("config") if isinstance(h.get("config"), dict) else {}
        if str(cfg.get("url") or "").rstrip("/") == GIT_HOOK_URL.rstrip("/"):
            match = h
            break
    body = {
        "name": "web",
        "active": True,
        "events": list(REQUIRED_HOOK_EVENTS),
        "config": {"url": GIT_HOOK_URL, "content_type": "json", "insecure_ssl": "0"},
    }
    if match is None:
        create(body)
        log.info("webhook ensure create repo=%s", repo)
        return {"action": "create", "repo": repo}
    events = {str(e) for e in (match.get("events") or [])}
    active = bool(match.get("active", True))
    if want <= events and active:
        return {"action": "ok", "repo": repo}
    hid = match.get("id")
    patch(hid, body)
    log.info("webhook ensure repair repo=%s id=%s", repo, hid)
    return {"action": "repair", "repo": repo}


def ensure_served_webhooks(
    repos: list[str],
    *,
    list_hooks: Callable[[str], list],
    create: Callable[[dict], Any],
    patch: Callable[..., Any],
    file_stall: Callable[..., Any] | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> list[dict]:
    """Idempotent ensure for every served repo. Logs each action."""
    actions: list[dict] = []
    for repo in repos:
        r = ensure_repo_webhook(
            repo,
            list_hooks=list_hooks,
            create=create,
            patch=patch,
            file_stall=file_stall,
        )
        actions.append(r)
        if log_fn:
            log_fn(f"INFO webhook-ensure repo={repo} action={r.get('action')}")
    return actions


def tick(
    home: Path,
    *,
    now: float | None = None,
    post: Callable[[str, dict], dict] | None = None,
    fetch_user: Callable[[], dict] | None = None,
    get: Callable[[str], Any] | None = None,
    announce: Callable[[str], None] | None = None,
) -> dict:
    """Refresh allowance, dispatch next eligible job, time out stale Copilot accepts.

    FR #5267: first settle closed accepts and stranded nick=copilot rows.
    Dispatch stays off (and the Copilot API is not called) when the allowance
    file is absent or ``enabled`` is false.

    FR #5201: settle timeouts (with live artifact GET) before any new dispatch so
    a timed-out job is not immediately handed back to Copilot.
    """
    now_f = time.time() if now is None else float(now)
    settled = settle_stuck_accepted(home, now=now_f)
    out: dict[str, Any] = {
        "dispatched": 0,
        "timed_out": 0,
        "dropped": int(settled.get("dropped") or 0),
        "released": int(settled.get("released") or 0),
    }
    if not dispatch_enabled(home):
        out["disabled"] = True
        return out
    if cooldown_active(home, now=now_f):
        out["paused"] = True
        return out
    if fetch_user is not None:
        refresh_allowance(home, fetch_user=fetch_user, now=now_f)
    jobs = _load_jobs(home)
    for job in list(jobs.get("jobs") or []):
        r = handle_timeout_or_fail(home, job, now=now_f, reason="timeout", get=get)
        if r.get("status") == "giveup":
            out["timed_out"] += 1
    ledger = gitclaim.ledger_load(home)
    active = {
        (j.get("repo"), j.get("task"), j.get("id"))
        for j in _load_jobs(home).get("jobs") or []
    }
    if has_allowance(home, now=now_f):
        catalog = []
        with contextlib.suppress(Exception):
            import stuck_job_sweep as _sjs5847

            catalog = list(_sjs5847.load_open_catalog(home) or [])
        qdoc = gitclaim.load_queue(home)
        for row in gitclaim.ordered_unaccepted(home):
            if (row.get("repo"), row.get("task"), row.get("id")) in active:
                continue
            if gitclaim.ledger_blocks(ledger, row, COPILOT_NICK):
                continue
            # FR #5847: never start a second Copilot task when a Copilot PR
            # already covers this FR (or DONE COPILOT_PR stamped).
            if str(row.get("task") or "").upper() == "FR":
                repo_r = str(row.get("repo") or "")
                ident_r = gitclaim._norm_row_id(row.get("id"))
                if _done_blocks_requeue(qdoc, repo_r, "FR", ident_r):
                    continue
                with contextlib.suppress(Exception):
                    import stuck_job_sweep as _sjs5847b

                    if _sjs5847b.find_copilot_pr_covering_fr(
                        catalog, repo=repo_r, issue_id=ident_r
                    ) is not None:
                        continue
                if _live_copilot_pr_url(qdoc, row, _matching_job(home, row)):
                    continue
            if is_high_priority(home, row) and should_dispatch(
                row, allowance=True, now=now_f
            ):
                r = dispatch_row(
                    home, row, post=post, now=now_f, announce=announce
                )
                if r.get("status") == "dispatched":
                    out["dispatched"] += 1
                break
    return out
