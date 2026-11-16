"""FR #7941: mark a finished Copilot draft PR ready for review and queue its MRB.

Only the Copilot coding agent is touched. A human draft is left alone.
A red or pending check, an in-progress Copilot session, or a head that is
still only the Initial plan commit stays draft. The same head SHA is
announced and unmarked once.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_QUIET_S = 300.0
_FAIL = {"FAILURE", "CANCELLED", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED"}


def quiet_seconds(raw: str | None = None) -> float:
    text = raw if raw is not None else os.environ.get("BOB_COPILOT_DRAFT_QUIET_S", "")
    try:
        n = float(str(text).strip() or DEFAULT_QUIET_S)
    except ValueError:
        return DEFAULT_QUIET_S
    if n < 0:
        return DEFAULT_QUIET_S
    return n


def _login(pr: dict) -> str:
    author = pr.get("author")
    if isinstance(author, dict):
        return str(author.get("login") or author.get("name") or "")
    user = pr.get("user") if isinstance(pr.get("user"), dict) else {}
    return str(pr.get("author_login") or user.get("login") or author or "")


def _commits(pr: dict) -> list[dict]:
    raw = pr.get("commits") or []
    if isinstance(raw, dict):
        raw = raw.get("nodes") or raw.get("commits") or []
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append({"message": item})
        elif isinstance(item, dict):
            msg = item.get("message") or item.get("messageHeadline") or ""
            commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
            if not msg:
                msg = commit.get("message") or commit.get("messageHeadline") or ""
            out.append({"message": str(msg)})
    return out


def _is_plan(message: str) -> bool:
    return str(message or "").strip().lower().startswith("initial plan")


def _checks(pr: dict) -> list[dict]:
    raw = pr.get("checks")
    if raw is None:
        raw = pr.get("statusCheckRollup") or []
    if isinstance(raw, dict):
        raw = raw.get("nodes") or []
    return [c for c in raw if isinstance(c, dict)]


def _copilot_wip(pr: dict, checks: list[dict]) -> bool:
    if pr.get("copilot_wip") is True:
        return True
    status = str(pr.get("copilot_status") or "").strip().lower()
    if status in ("in_progress", "in-progress", "working", "queued"):
        return True
    for check in checks:
        name = str(check.get("name") or check.get("context") or "").lower()
        if "copilot" not in name:
            continue
        state = str(check.get("status") or "").upper()
        if state and state != "COMPLETED":
            return True
    return False


def block_reason(pr: dict, now: float, quiet_s: float | None = None) -> str:
    """Empty string when this draft may be marked ready. Otherwise why not."""
    import gitclaim

    if not isinstance(pr, dict):
        return "not-a-pr"
    if pr.get("draft") is False or pr.get("isDraft") is False:
        return "not-draft"
    if not gitclaim.is_copilot_agent_login(_login(pr)):
        return "not-copilot"
    if _copilot_wip(pr, _checks(pr)):
        return "copilot-wip"
    commits = _commits(pr)
    if not commits or all(_is_plan(c.get("message") or "") for c in commits):
        return "initial-plan-only"
    quiet = DEFAULT_QUIET_S if quiet_s is None else float(quiet_s)
    try:
        pushed = float(pr.get("pushed_at") or 0.0)
    except (TypeError, ValueError):
        pushed = 0.0
    if pushed <= 0:
        return "no-push-time"
    if float(now) - pushed < quiet:
        return "quiet-period"
    checks = _checks(pr)
    if not checks:
        return "checks-missing"
    for check in checks:
        state = str(check.get("status") or "").upper()
        conclusion = str(check.get("conclusion") or "").upper()
        if state != "COMPLETED":
            return "checks-pending"
        if conclusion in _FAIL or conclusion not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            return "checks-failed"
    return ""


def _state_path(home: Path) -> Path:
    return Path(home) / "copilot-draft-ready.json"


def _load_done(home: Path) -> dict:
    try:
        doc = json.loads(_state_path(home).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    done = doc.get("done") if isinstance(doc, dict) else None
    return dict(done) if isinstance(done, dict) else {}


def _save_done(home: Path, done: dict) -> None:
    path = _state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"v": 1, "done": done}, indent=2) + "\n", encoding="utf-8")


def _sha(pr: dict) -> str:
    return str(pr.get("sha") or pr.get("headRefOid") or pr.get("head_sha") or "").strip()


def _key(pr: dict) -> str:
    repo = str(pr.get("repo") or "").strip()
    num = str(pr.get("number") or "").strip().lstrip("#")
    return f"{repo}#{num}"


def _enqueue_mrb(home: Path, pr: dict) -> None:
    import bobreport

    repo = str(pr.get("repo") or "").strip()
    num = int(str(pr.get("number")).lstrip("#"))
    payload = {
        "action": "ready_for_review",
        "repository": {"full_name": repo},
        "pull_request": {
            "number": num,
            "title": str(pr.get("title") or f"pr {num}"),
            "body": str(pr.get("body") or ""),
            "draft": False,
            "merged": False,
            "state": "open",
            "html_url": f"https://github.com/{repo}/pull/{num}",
            "labels": [],
            "user": {"login": _login(pr)},
        },
    }
    bobreport.apply_git_webhook(home, "pull_request", payload)


def repos_to_scan(home: Path) -> list[str]:
    found: list[str] = []
    extra = os.environ.get("BOB_COPILOT_DRAFT_REPOS", "")
    for part in str(extra or "").split(","):
        text = part.strip()
        if text and text not in found:
            found.append(text)
    try:
        import focus_ignore

        doc = focus_ignore.load_focus(home)
        for key in (doc.get("repos") or {}):
            text = str(key).strip()
            if text and text not in found:
                found.append(text)
    except Exception:
        pass
    if not found:
        found.append("SimonBarnett/bobiverse")
    return found


def _epoch(raw: str) -> float:
    import gitclaim

    got = gitclaim._parse_iso_ts(str(raw or ""))
    return float(got or 0.0)


def list_open_copilot_drafts(repos: list[str]) -> list[dict]:
    """Open draft PRs by the Copilot agent. Empty when gh is unavailable."""
    import subprocess

    import gitclaim

    out: list[dict] = []
    for repo in repos:
        try:
            proc = subprocess.run(
                [
                    "gh", "pr", "list", "--repo", repo, "--state", "open",
                    "--draft", "--limit", "20",
                    "--json", "number,title,author,isDraft,updatedAt,headRefOid,statusCheckRollup",
                ],
                capture_output=True, text=True, timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0 or not proc.stdout.strip():
            continue
        try:
            rows = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            author = row.get("author") if isinstance(row.get("author"), dict) else {}
            login = str(author.get("login") or "")
            if not gitclaim.is_copilot_agent_login(login):
                continue
            num = row.get("number")
            commits: list[dict] = []
            try:
                view = subprocess.run(
                    [
                        "gh", "pr", "view", str(num), "--repo", repo,
                        "--json", "commits,statusCheckRollup,updatedAt,headRefOid",
                    ],
                    capture_output=True, text=True, timeout=20,
                )
                if view.returncode == 0 and view.stdout.strip():
                    detail = json.loads(view.stdout)
                    if isinstance(detail, dict):
                        commits = _commits(detail)
                        row = {**row, **detail}
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
                commits = []
            out.append(
                {
                    "repo": repo,
                    "number": num,
                    "title": row.get("title") or "",
                    "draft": True,
                    "author": {"login": login},
                    "sha": row.get("headRefOid") or "",
                    "pushed_at": _epoch(str(row.get("updatedAt") or "")),
                    "commits": commits,
                    "checks": _checks(row),
                }
            )
    return out


def gh_mark_ready(pr: dict) -> bool:
    import subprocess

    repo = str(pr.get("repo") or "")
    num = str(pr.get("number") or "").lstrip("#")
    if not repo or not num:
        return False
    try:
        proc = subprocess.run(
            ["gh", "pr", "ready", num, "--repo", repo],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def promote(
    home: Path,
    prs: list[dict],
    *,
    now: float,
    quiet_s: float | None = None,
    mark_ready=None,
    announce=None,
    log=None,
) -> list[str]:
    """Mark finished Copilot drafts ready. Returns the keys marked this call."""
    quiet = quiet_seconds() if quiet_s is None else float(quiet_s)
    done = _load_done(home)
    marked: list[str] = []
    for pr in prs or []:
        if not isinstance(pr, dict):
            continue
        key = _key(pr)
        sha = _sha(pr)
        if not key or key.endswith("#") or not sha:
            continue
        if str(done.get(key) or "") == sha:
            continue
        reason = block_reason(pr, now, quiet)
        if reason:
            if log:
                log(f"INFO copilot-draft-ready skip {key} reason={reason}")
            continue
        if mark_ready is not None and mark_ready(pr) is False:
            if log:
                log(f"WARN copilot-draft-ready mark failed {key}")
            continue
        done[key] = sha
        _save_done(home, done)
        try:
            _enqueue_mrb(home, pr)
        except Exception as exc:
            if log:
                log(f"WARN copilot-draft-ready enqueue {key} {type(exc).__name__}")
        line = f"INFO copilot-draft-ready {key} sha={sha} marked ready for review"
        if log:
            log(line)
        if announce:
            announce(line)
        marked.append(key)
    return marked
