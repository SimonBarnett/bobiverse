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
import time
from pathlib import Path
from typing import Any, Callable

import bobreport
import gitclaim
import shop_listen

log = logging.getLogger("copilot_dispatch")

COPILOT_NICK = "copilot"
GIT_HOOK_URL = "https://irc.ntsa.uk/bob/v1/git"
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
FUEL_COOLDOWN_S = {"copilot": COPILOT_COOLDOWN_S}
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


def set_allowance(home: Path, remaining: int | None = None, exhausted: bool | None = None) -> None:
    doc = load_allowance(home)
    if remaining is not None:
        doc["remaining"] = int(remaining)
        doc["exhausted"] = int(remaining) <= 0
        if int(remaining) > 0:
            doc["tasks_exhausted"] = False
            doc["state"] = "ok"
            doc.pop("exhausted_until", None)
            doc.pop("exhausted_until_utc", None)
            doc.pop("pause_announced_until", None)
    if exhausted is not None:
        doc["exhausted"] = bool(exhausted)
        if not exhausted:
            doc["tasks_exhausted"] = False
            doc.pop("exhausted_until", None)
            doc.pop("exhausted_until_utc", None)
            doc.pop("pause_announced_until", None)
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


def cooldown_active(home: Path, *, now: float | None = None, fuel: str = "copilot") -> bool:
    _ = fuel
    now_f = time.time() if now is None else float(now)
    until = _num(load_allowance(home).get("exhausted_until"))
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
        mark_tokens_exhausted(home, now=now_f)
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
) -> dict[str, Any]:
    """FR #5316: persist per-fuel cooldown; Copilot is 7 days. No probing until then."""
    now_f = time.time() if now is None else float(now)
    until = now_f + fuel_cooldown_seconds(fuel)
    doc = load_allowance(home)
    already = _num(doc.get("exhausted_until"))
    doc["tasks_exhausted"] = True
    doc["exhausted"] = True
    doc["state"] = "exhausted"
    doc["exhausted_until"] = until
    doc["exhausted_until_utc"] = _utc_iso(until)
    doc["fuel"] = (fuel or "copilot").strip().lower()
    Path(home).mkdir(parents=True, exist_ok=True)
    released = release_held_copilot_rows(home)
    line = f"Copilot out of tokens - paused until {doc['exhausted_until_utc']}"
    announced = doc.get("pause_announced_until")
    if announced != until:
        doc["pause_announced_until"] = until
        if announce:
            announce(line)
        else:
            with contextlib.suppress(Exception):
                bobreport.enqueue_chair_fleet_privmsg(home, line)
    _allow_path(home).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    _ = already
    return {"exhausted_until": until, "released": released, "line": line}


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


def should_dispatch(row: dict, *, allowance: bool) -> bool:
    if not allowance:
        return False
    task = str(row.get("task") or "").upper()
    if task not in ("FR", "FIX", "MRB"):
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
    if not should_dispatch(row, allowance=True):
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


def handle_timeout_or_fail(
    home: Path, job: dict, *, now: float, reason: str = "timeout"
) -> dict:
    """Give-up semantics: stamp copilot on giveup_seats and requeue (no instant re-offer)."""
    repo = str(job.get("repo") or "")
    task = str(job.get("task") or "FR").upper()
    ident = str(job.get("id") or "")
    started = float(job.get("started") or 0)
    if reason == "timeout" and started and (now - started) < TASK_TIMEOUT_S:
        return {"status": "pending"}
    try:
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            acc = doc.get("accepted") or []
            keep = []
            moved = None
            for r in acc:
                if (
                    str(r.get("repo")) == repo
                    and str(r.get("id")) == ident
                    and str(r.get("task") or "").upper() == task
                    and str(r.get("nick") or "") == COPILOT_NICK
                ):
                    moved = dict(r)
                else:
                    keep.append(r)
            doc["accepted"] = keep
            if moved is None:
                moved = {"repo": repo, "task": task, "id": ident}
            seats = [
                s.strip()
                for s in str(moved.get("giveup_seats") or "").split(",")
                if s.strip()
            ]
            if COPILOT_NICK not in {s.lower() for s in seats}:
                seats.append(COPILOT_NICK)
            moved["giveup_seats"] = ",".join(seats)
            moved.pop("nick", None)
            moved.pop("accepted_ts", None)
            un = doc.setdefault("unaccepted", [])
            if not any(
                str(r.get("repo")) == repo
                and str(r.get("id")) == ident
                and str(r.get("task") or "").upper() == task
                for r in un
            ):
                un.append(moved)
            gitclaim._write_queue(gitclaim.queue_path(home), doc)
    except (TimeoutError, OSError, ValueError):
        return {"status": "error"}
    jobs = _load_jobs(home)
    jobs["jobs"] = [
        j
        for j in jobs.get("jobs") or []
        if not (j.get("repo") == repo and j.get("id") == ident and j.get("task") == task)
    ]
    _save_jobs(home, jobs)
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
    announce: Callable[[str], None] | None = None,
) -> dict:
    """Refresh allowance, dispatch next eligible job, time out stale Copilot accepts."""
    now_f = time.time() if now is None else float(now)
    if cooldown_active(home, now=now_f):
        return {"dispatched": 0, "timed_out": 0, "paused": True}
    if fetch_user is not None:
        refresh_allowance(home, fetch_user=fetch_user, now=now_f)
    out: dict[str, Any] = {"dispatched": 0, "timed_out": 0}
    if has_allowance(home, now=now_f):
        for row in gitclaim.load_unaccepted(home):
            if should_dispatch(row, allowance=True):
                r = dispatch_row(
                    home, row, post=post, now=now_f, announce=announce
                )
                if r.get("status") == "dispatched":
                    out["dispatched"] += 1
                break
    jobs = _load_jobs(home)
    for job in list(jobs.get("jobs") or []):
        r = handle_timeout_or_fail(home, job, now=now_f, reason="timeout")
        if r.get("status") == "giveup":
            out["timed_out"] += 1
    return out
