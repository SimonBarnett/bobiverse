"""FR #5317 / #5394 / #5865: optional CodeRabbit / Copilot / fleet fuel stages.

Each stage is off by default and never load-bearing. When ``BOB_FUEL_CODERABBIT``
is on and the product repo has CodeRabbit present, Jeeves holds an MRB offer
until a review covers the current head SHA, CodeRabbit fails/skips, silence
marks the app absent (2 min), or ``BOB_CODERABBIT_WAIT_MIN`` (default 12)
elapses (``coderabbit=timeout``). Removing ``.coderabbit.yaml`` or the app
turns the mode off cleanly (``coderabbit=absent``). Copilot is never required
for a fleet offer.
"""
from __future__ import annotations

import fnmatch
import os
import re
import time
from typing import Any, Callable, Iterable

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_CR_BOT = re.compile(r"(?i)^coderabbitai(\[bot\])?$")
_CR_CHECK = re.compile(r"(?i)coderabbit")
_CR_FAIL = re.compile(r"(?i)review\s+failed")
_CR_SKIP = re.compile(r"(?i)review\s+skipped|skip review by coderabbit")
_CR_SKIP_IGNORE = re.compile(r"(?i)ignore keyword")
_CR_SKIP_CLOSED = re.compile(r"(?i)pr is closed|pull request is closed")
_CR_SKIP_BASE = re.compile(r"(?i)non-default base|not the default branch")
_DEFAULT_WAIT_MIN = 12.0
_ABSENT_SILENCE_S = 120.0
_YAML_CACHE_S = 30 * 60.0

# FR #5865: always full review for credential / install / updater / workflow paths.
_SENSITIVE_GLOBS = (
    "**/*cred*",
    "**/*secret*",
    "**/*password*",
    "**/crash_report*",
    "**/*redact*",
    "**/Install-*.ps1",
    "**/Update-*.ps1",
    "**/*installer*/**",
    "**/*.wxs",
    "common/scripts/intake.py",
    ".github/workflows/**",
)

# repo -> (present: bool, fetched_at: float)
_yaml_cache: dict[str, tuple[bool, float]] = {}


def stage_enabled(name: str, *, env: dict | None = None) -> bool:
    """True only when the named stage env is an explicit on-value."""
    key = {
        "coderabbit": "BOB_FUEL_CODERABBIT",
        "copilot": "BOB_FUEL_COPILOT",
        "fleet": "BOB_FUEL_FLEET",
    }.get(str(name or "").strip().lower())
    if not key:
        return False
    src = env if env is not None else os.environ
    return str(src.get(key) or "").strip().lower() in _TRUTHY


def active_stages(*, env: dict | None = None) -> tuple[str, ...]:
    return tuple(n for n in ("coderabbit", "copilot", "fleet") if stage_enabled(n, env=env))


def wait_seconds(*, env: dict | None = None) -> float:
    src = env if env is not None else os.environ
    raw = str(src.get("BOB_CODERABBIT_WAIT_MIN") or str(int(_DEFAULT_WAIT_MIN))).strip()
    try:
        mins = float(raw)
    except ValueError:
        mins = _DEFAULT_WAIT_MIN
    if mins < 0:
        mins = _DEFAULT_WAIT_MIN
    return mins * 60.0


def absent_silence_seconds(*, env: dict | None = None) -> float:
    src = env if env is not None else os.environ
    raw = str(src.get("BOB_CODERABBIT_ABSENT_SEC") or str(int(_ABSENT_SILENCE_S))).strip()
    try:
        secs = float(raw)
    except ValueError:
        secs = _ABSENT_SILENCE_S
    if secs < 0:
        secs = _ABSENT_SILENCE_S
    return secs


def is_coderabbit_check_name(name: str) -> bool:
    return bool(_CR_CHECK.search(str(name or "")))


def sha_covers(left: str, right: str) -> bool:
    """True when either SHA is empty-free and one is a prefix of the other."""
    a = str(left or "").strip().lower()
    b = str(right or "").strip().lower()
    if not a or not b:
        return False
    return a.startswith(b) or b.startswith(a)


def coderabbit_skip_why(text: str) -> str:
    """Return a stable skip reason token, or '' when *text* is not a skip."""
    body = str(text or "")
    if not _CR_SKIP.search(body):
        return ""
    if _CR_SKIP_CLOSED.search(body):
        return "pr-closed"
    if _CR_SKIP_BASE.search(body):
        return "non-default-base"
    if _CR_SKIP_IGNORE.search(body):
        return "ignore-keyword"
    return "skipped"


def sensitive_paths_require_full(paths: Iterable[str] | None) -> bool:
    """True when any changed path matches the FR #5865 always-full list."""
    for raw in paths or []:
        # Strip only ./ prefixes and leading /; never lstrip("./")
        # (char-class form drops the leading dot from .github/workflows/**).
        path = str(raw or "").replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        path = path.lstrip("/")
        if not path:
            continue
        for pat in _SENSITIVE_GLOBS:
            if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path.lower(), pat.lower()):
                return True
            # Also match basename-only patterns against the leaf.
            leaf = path.rsplit("/", 1)[-1]
            if "*" in pat and "/" not in pat.rstrip("*") and fnmatch.fnmatch(leaf, pat):
                return True
    return False


def review_mode_for(cr_mode: str, paths: Iterable[str] | None = None) -> str:
    """``light`` only when stamp is ready and no sensitive paths; else ``full``."""
    mode = str(cr_mode or "").strip().lower()
    # skipped:<why> / failed / timeout / off / absent / pending → full
    if mode == "ready" and not sensitive_paths_require_full(paths):
        return "light"
    return "full"


def coderabbit_reviewed_head(
    reviews: Iterable[dict] | None,
    checks: Iterable[dict] | None,
    head_sha: str,
) -> bool:
    """True when a CodeRabbit review or completed check covers ``head_sha``."""
    want = str(head_sha or "").strip().lower()
    if not want:
        return False
    for rev in reviews or []:
        if not isinstance(rev, dict):
            continue
        user = rev.get("user") if isinstance(rev.get("user"), dict) else {}
        login = str(user.get("login") or rev.get("login") or "").strip()
        commit = str(rev.get("commit_id") or rev.get("commitId") or "").strip().lower()
        body = str(rev.get("body") or "")
        if (
            _CR_BOT.match(login)
            and sha_covers(commit, want)
            and not _CR_FAIL.search(body)
            and not coderabbit_skip_why(body)
        ):
            return True
    for chk in checks or []:
        if not isinstance(chk, dict):
            continue
        name = str(chk.get("name") or chk.get("context") or "")
        if not _CR_CHECK.search(name):
            continue
        csha = str(chk.get("head_sha") or chk.get("headSha") or "").strip().lower()
        status = str(chk.get("status") or "").strip().lower()
        conclusion = str(chk.get("conclusion") or "").strip().lower()
        if sha_covers(csha, want) and status in ("", "completed"):
            if conclusion in ("failure", "timed_out", "cancelled", "canceled", "skipped"):
                continue
            return True
    return False


def coderabbit_failed_head(
    reviews: Iterable[dict] | None,
    checks: Iterable[dict] | None,
    comments: Iterable[dict] | None,
    head_sha: str = "",
) -> bool:
    """True when CodeRabbit posted Review failed (not skipped) for this PR/head."""
    want = str(head_sha or "").strip().lower()
    for rev in reviews or []:
        if not isinstance(rev, dict):
            continue
        user = rev.get("user") if isinstance(rev.get("user"), dict) else {}
        login = str(user.get("login") or rev.get("login") or "").strip()
        if not _CR_BOT.match(login):
            continue
        commit = str(rev.get("commit_id") or rev.get("commitId") or "").strip().lower()
        if want and commit and not sha_covers(commit, want):
            continue
        body = str(rev.get("body") or "")
        if coderabbit_skip_why(body):
            continue
        if _CR_FAIL.search(body):
            return True
    for c in comments or []:
        if not isinstance(c, dict):
            continue
        user = c.get("user") if isinstance(c.get("user"), dict) else {}
        login = str(user.get("login") or c.get("login") or "").strip()
        if not _CR_BOT.match(login):
            continue
        body = str(c.get("body") or "")
        if coderabbit_skip_why(body):
            continue
        if _CR_FAIL.search(body):
            return True
    for chk in checks or []:
        if not isinstance(chk, dict):
            continue
        name = str(chk.get("name") or chk.get("context") or "")
        if not _CR_CHECK.search(name):
            continue
        csha = str(chk.get("head_sha") or chk.get("headSha") or "").strip().lower()
        if want and csha and not sha_covers(csha, want):
            continue
        status = str(chk.get("status") or "").strip().lower()
        conclusion = str(chk.get("conclusion") or "").strip().lower()
        if status == "completed" and conclusion in (
            "failure",
            "timed_out",
            "cancelled",
            "canceled",
        ):
            return True
    return False


def coderabbit_skipped_head(
    reviews: Iterable[dict] | None,
    comments: Iterable[dict] | None,
    checks: Iterable[dict] | None = None,
    head_sha: str = "",
) -> str:
    """Return skip why-token when CodeRabbit skipped; else ''."""
    want = str(head_sha or "").strip().lower()
    for rev in reviews or []:
        if not isinstance(rev, dict):
            continue
        user = rev.get("user") if isinstance(rev.get("user"), dict) else {}
        login = str(user.get("login") or rev.get("login") or "").strip()
        if not _CR_BOT.match(login):
            continue
        commit = str(rev.get("commit_id") or rev.get("commitId") or "").strip().lower()
        if want and commit and not sha_covers(commit, want):
            continue
        why = coderabbit_skip_why(str(rev.get("body") or ""))
        if why:
            return why
    for c in comments or []:
        if not isinstance(c, dict):
            continue
        user = c.get("user") if isinstance(c.get("user"), dict) else {}
        login = str(user.get("login") or c.get("login") or "").strip()
        if not _CR_BOT.match(login):
            continue
        why = coderabbit_skip_why(str(c.get("body") or ""))
        if why:
            return why
    for chk in checks or []:
        if not isinstance(chk, dict):
            continue
        name = str(chk.get("name") or chk.get("context") or "")
        if not _CR_CHECK.search(name):
            continue
        csha = str(chk.get("head_sha") or chk.get("headSha") or "").strip().lower()
        if want and csha and not sha_covers(csha, want):
            continue
        status = str(chk.get("status") or "").strip().lower()
        conclusion = str(chk.get("conclusion") or "").strip().lower()
        if status == "completed" and conclusion == "skipped":
            return "check-skipped"
    return ""


def coderabbit_state_from_surfaces(
    *,
    reviews: Iterable[dict] | None = None,
    checks: Iterable[dict] | None = None,
    comments: Iterable[dict] | None = None,
    head_sha: str = "",
) -> dict[str, Any]:
    """Classify ready/failed/skipped/activity from reviews, checks, and comments."""
    want = str(head_sha or "").strip()
    skip_why = coderabbit_skipped_head(reviews, comments, checks, want)
    failed = coderabbit_failed_head(reviews, checks, comments, want)
    activity = coderabbit_activity_seen(reviews, checks, comments)
    ready = False
    if not skip_why and not failed:
        if want:
            ready = coderabbit_reviewed_head(reviews, checks, want)
        else:
            ready = activity
    return {
        "ready": bool(ready),
        "failed": bool(failed),
        "skipped": bool(skip_why),
        "skip_why": skip_why or "",
        "activity": bool(activity or ready or failed or skip_why),
    }


def coderabbit_activity_seen(
    reviews: Iterable[dict] | None,
    checks: Iterable[dict] | None,
    comments: Iterable[dict] | None,
) -> bool:
    """True when any CodeRabbit bot comment/review/check has appeared."""
    for rev in reviews or []:
        if not isinstance(rev, dict):
            continue
        user = rev.get("user") if isinstance(rev.get("user"), dict) else {}
        if _CR_BOT.match(str(user.get("login") or rev.get("login") or "").strip()):
            return True
    for c in comments or []:
        if not isinstance(c, dict):
            continue
        user = c.get("user") if isinstance(c.get("user"), dict) else {}
        if _CR_BOT.match(str(user.get("login") or c.get("login") or "").strip()):
            return True
    for chk in checks or []:
        if not isinstance(chk, dict):
            continue
        if _CR_CHECK.search(str(chk.get("name") or chk.get("context") or "")):
            return True
    return False


def _gh_get_json(url: str, token: str) -> Any:
    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-fuel-chain",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def repo_has_coderabbit_yaml(
    repo: str,
    *,
    now: float | None = None,
    token: str | None = None,
    force: bool = False,
) -> bool:
    """Cached GET of ``.coderabbit.yaml`` on the default branch (30 min)."""
    repo_s = str(repo or "").strip()
    if not repo_s:
        return False
    ts = float(now if now is not None else time.time())
    cached = _yaml_cache.get(repo_s)
    if cached is not None and not force and (ts - cached[1]) < _YAML_CACHE_S:
        return cached[0]
    tok = (token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not tok:
        # Fail-open as present so a missing token does not force absent; live
        # silence / timeout still ends the wait.
        return True
    present = False
    try:
        import urllib.error

        try:
            _gh_get_json(
                f"https://api.github.com/repos/{repo_s}/contents/.coderabbit.yaml",
                tok,
            )
            present = True
        except urllib.error.HTTPError as exc:
            if int(getattr(exc, "code", 0) or 0) == 404:
                present = False
            else:
                present = True
        except Exception:
            present = True
    except Exception:
        present = True
    _yaml_cache[repo_s] = (present, ts)
    return present


def clear_yaml_cache() -> None:
    _yaml_cache.clear()


def lookup_coderabbit_reviewed(repo: str, num: str, head: str = "") -> bool:
    """Live GitHub lookup. Fail-open as 'not yet' (timeout still offers). No secrets logged."""
    state = lookup_coderabbit_state(repo, num, head)
    return bool(state.get("ready"))


def lookup_coderabbit_state(repo: str, num: str, head: str = "") -> dict[str, Any]:
    """Return ``{ready, failed, skipped, skip_why, activity}`` from live GitHub.

    FR #6434: reviews + issue comments (skip walkthrough) + check-runs on head.
    Fail-open quiet when token/network missing.
    """
    out: dict[str, Any] = {
        "ready": False,
        "failed": False,
        "skipped": False,
        "skip_why": "",
        "activity": False,
    }
    repo_s = str(repo or "").strip()
    num_s = str(num or "").strip().lstrip("#")
    if not repo_s or not num_s.isdigit():
        return out
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return out
    reviews: list = []
    comments: list = []
    checks: list = []
    try:
        raw = _gh_get_json(
            f"https://api.github.com/repos/{repo_s}/pulls/{num_s}/reviews",
            token,
        )
        if isinstance(raw, list):
            reviews = raw
    except Exception:
        reviews = []
    try:
        raw = _gh_get_json(
            f"https://api.github.com/repos/{repo_s}/issues/{num_s}/comments?per_page=100",
            token,
        )
        if isinstance(raw, list):
            comments = raw
    except Exception:
        comments = []
    want = str(head or "").strip()
    if want:
        try:
            raw = _gh_get_json(
                f"https://api.github.com/repos/{repo_s}/commits/{want}/check-runs",
                token,
            )
            if isinstance(raw, dict) and isinstance(raw.get("check_runs"), list):
                checks = list(raw.get("check_runs") or [])
            elif isinstance(raw, list):
                checks = raw
        except Exception:
            checks = []
    return coderabbit_state_from_surfaces(
        reviews=reviews, checks=checks, comments=comments, head_sha=want
    )


def mrb_coderabbit_offer(
    row: dict,
    *,
    now: float,
    enabled: bool,
    has_review: bool,
    wait_s: float,
    first_seen: float | None = None,
    has_yaml: bool = True,
    failed: bool = False,
    skipped: bool = False,
    skip_why: str = "",
    activity: bool = False,
    silence_s: float = _ABSENT_SILENCE_S,
) -> tuple[bool, str]:
    """Return (hold_offer, stamp). Never load-bearing: timeout/off/absent all offer."""
    if not enabled:
        return False, "off"
    if not has_yaml:
        return False, "absent"
    if skipped:
        why = str(skip_why or "").strip()
        if why.startswith("skipped"):
            return False, why
        if why:
            return False, f"skipped:{why}"
        return False, "skipped"
    if failed:
        return False, "failed"
    if has_review:
        return False, "ready"
    since = first_seen
    if since is None:
        try:
            since = float(row.get("coderabbit_wait_since"))
        except (TypeError, ValueError):
            since = now
    try:
        age = float(now) - float(since)
    except (TypeError, ValueError):
        age = 0.0
    if age >= float(silence_s) and not activity:
        return False, "absent"
    if age >= float(wait_s):
        return False, "timeout"
    return True, "pending"


def _row_changed_files(row: dict) -> list[str]:
    raw = row.get("changed_files") or row.get("files") or row.get("paths") or []
    if isinstance(raw, str):
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(p) for p in raw if str(p).strip()]
    return []


def apply_mrb_coderabbit_gate(row: dict, now: float, *, lookup=None) -> bool:
    """Mutate ``row`` stamps. Return True when the offer must wait.

    FR #5394: prefer stamped ``coderabbit=ready`` (webhook) on the *current*
    head. Live lookup is optional and must be the caller's budgeted checker
    on ``!bored``. FR #5865: always stamp ``coderabbit=`` + ``review=``.
    """
    if not isinstance(row, dict):
        return False
    if str(row.get("task") or "").strip().upper() != "MRB":
        return False

    head = str(row.get("head_sha") or "").strip().lower()
    prev_head = str(row.get("coderabbit_head_sha") or "").strip().lower()
    if head and prev_head and head != prev_head:
        # New push resets the wait window and clears a stale ready stamp.
        row["coderabbit_wait_since"] = float(now)
        prev_stamp = str(row.get("coderabbit") or "").strip().lower()
        if prev_stamp in ("ready", "failed", "timeout", "absent") or prev_stamp.startswith("skipped"):
            row["coderabbit"] = "pending"
    if head:
        row["coderabbit_head_sha"] = head
    if "coderabbit_wait_since" not in row:
        row["coderabbit_wait_since"] = float(now)

    paths = _row_changed_files(row)

    if not stage_enabled("coderabbit"):
        row["coderabbit"] = "off"
        row["review"] = "full"
        return False

    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")

    has_yaml = True
    try:
        has_yaml = bool(repo_has_coderabbit_yaml(repo, now=now))
    except Exception:
        has_yaml = True

    ready = False
    failed = False
    skipped = False
    skip_why = ""
    activity = False
    stamped = str(row.get("coderabbit") or "").strip().lower()
    same_head = (not head) or (not prev_head) or (prev_head == head)
    if stamped == "ready" and same_head:
        ready = True
        activity = True
    elif stamped == "failed" and same_head:
        failed = True
        activity = True
    elif stamped.startswith("skipped") and same_head:
        skipped = True
        skip_why = stamped.split(":", 1)[1] if ":" in stamped else "skipped"
        activity = True
    else:
        try:
            if lookup is not None:
                # Budgeted checker (FR #5394): bool or state dict. Never fall through
                # to a second live HTTP GET.
                got = lookup(repo, num)
                if isinstance(got, dict):
                    ready = bool(got.get("ready"))
                    failed = bool(got.get("failed"))
                    skipped = bool(got.get("skipped"))
                    skip_why = str(got.get("skip_why") or "").strip()
                    activity = bool(got.get("activity"))
                else:
                    ready = bool(got)
                    # Bool-only budget path cannot see silence; keep pending until
                    # timeout rather than marking absent without evidence.
                    activity = True
            else:
                state = lookup_coderabbit_state(repo, num, head)
                ready = bool(state.get("ready"))
                failed = bool(state.get("failed"))
                skipped = bool(state.get("skipped"))
                skip_why = str(state.get("skip_why") or "").strip()
                activity = bool(state.get("activity"))
        except Exception:
            ready = False
            activity = True

    hold, tag = mrb_coderabbit_offer(
        row,
        now=now,
        enabled=True,
        has_review=ready,
        wait_s=wait_seconds(),
        first_seen=float(row.get("coderabbit_wait_since") or now),
        has_yaml=has_yaml,
        failed=failed,
        skipped=skipped,
        skip_why=skip_why,
        activity=activity,
        silence_s=absent_silence_seconds(),
    )
    row["coderabbit"] = tag or "pending"
    # FR #6434: durable reason for chair logs / assign diagnostics.
    if tag == "ready":
        row["coderabbit_reason"] = "ready:coderabbit-review-or-check"
    elif tag and str(tag).startswith("skipped"):
        row["coderabbit_reason"] = str(tag)
    elif tag in ("failed", "timeout", "absent", "off", "pending"):
        row["coderabbit_reason"] = str(tag)
    row["review"] = review_mode_for(row["coderabbit"], paths)
    return hold


def assign_suffix(row: dict) -> str:
    """Append ``coderabbit=<mode>`` and ``review=<light|full>`` when stamped."""
    parts: list[str] = []
    tag = str((row or {}).get("coderabbit") or "").strip().lower()
    if tag:
        parts.append(f"coderabbit={tag}")
    review = str((row or {}).get("review") or "").strip().lower()
    if review in ("light", "full"):
        parts.append(f"review={review}")
    elif tag:
        parts.append(f"review={review_mode_for(tag, _row_changed_files(row or {}))}")
    return " ".join(parts)


def coderabbit_hold_message(row: dict, now: float) -> str:
    """Actionable refuse/log detail for a pending CodeRabbit MRB hold (FR #6211)."""
    repo = str((row or {}).get("repo") or "").strip() or "?"
    num = str((row or {}).get("id") or "").strip().lstrip("#") or "?"
    stamp = str((row or {}).get("coderabbit") or "pending").strip().lower() or "pending"
    wait_s = float(wait_seconds())
    try:
        since = float((row or {}).get("coderabbit_wait_since") or now)
    except (TypeError, ValueError):
        since = float(now)
    try:
        age = max(0.0, float(now) - since)
    except (TypeError, ValueError):
        age = 0.0
    rem = max(0.0, wait_s - age)
    return (
        f"coderabbit_hold {repo}#{num} stamp={stamp} "
        f"age_s={int(age)} rem_s={int(rem)}"
    )


def gate_cleared(stamp: str) -> bool:
    """True when merge/offer may proceed for this CodeRabbit stamp."""
    mode = str(stamp or "").strip().lower()
    if mode.startswith("skipped"):
        return True
    return mode in (
        "ready",
        "failed",
        "timeout",
        "off",
        "absent",
    )
