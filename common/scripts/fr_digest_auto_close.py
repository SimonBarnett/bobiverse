#!/usr/bin/env python3
"""FR #9552: auto-close ``fr-digest`` when the last open Depends-on child closes.

Ticket-closure / chair reconcile path. Idempotent: never reopens; skips digests
with ``hold`` / ``on-hold``; no-ops when the digest is already closed or when any
other open child still Depends-on it.

Marker ``bob_fr9552_auto_close_digest`` is intentional for tip/monitor soft-ok.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Iterable


def _load_common_depends_on():
    """FR #9540: load sibling ``depends_on.py`` (never monitor shadow)."""
    name = "bobiverse_common_depends_on"
    cached = sys.modules.get(name)
    if cached is not None and hasattr(cached, "parse_depends_on"):
        return cached
    path = Path(__file__).resolve().with_name("depends_on.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load common depends_on from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[name] = mod
    return mod


def parse_depends_on(body: str | None, repo: str = ""):
    return _load_common_depends_on().parse_depends_on(body, repo=repo)


def _child_depends_on_parent(
    body: str | None,
    child_repo: str,
    parent_repo: str,
    parent_num: int,
) -> bool:
    home = _canon_repo(child_repo) or _canon_repo(parent_repo)
    pref = _canon_repo(parent_repo).lower()
    for repo, num in parse_depends_on(body, repo=home):
        r = (_canon_repo(repo) or home).lower()
        if r == pref and int(num) == int(parent_num):
            return True
    return False


def find_open_children(
    parent_repo: str,
    parent_num: int | str,
    issues: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Open issues whose Depends-on resolves to ``parent_repo#parent_num``."""
    pref = _canon_repo(parent_repo)
    pnum = _canon_num(parent_num)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for raw in issues:
        if not isinstance(raw, dict):
            continue
        state = str(raw.get("state") or "open").strip().lower()
        if state and state not in ("open", "opened"):
            continue
        try:
            num = int(str(raw.get("number") or "").strip().lstrip("#"))
        except ValueError:
            continue
        repo = _canon_repo(str(raw.get("repo") or ""))
        if not repo and isinstance(raw.get("repository"), dict):
            repo = _canon_repo(str(raw["repository"].get("full_name") or ""))
        if not repo:
            repo = pref
        if _child_depends_on_parent(raw.get("body"), repo, pref, pnum):
            key = (repo.lower(), num)
            if key in seen:
                continue
            seen.add(key)
            row = dict(raw)
            row.setdefault("repo", repo)
            out.append(row)
    out.sort(key=lambda r: (str(r.get("repo") or ""), int(r.get("number") or 0)))
    return out

# Tip marker (do not rename without updating monitor soft-ok pins).
bob_fr9552_auto_close_digest = True

DIGEST_LABELS = frozenset({"fr-digest", "digest"})
HOLD_LABELS = frozenset({"hold", "on-hold"})

FetchIssue = Callable[[str, int], dict[str, Any] | None]
ListOpenIssues = Callable[[str], list[dict[str, Any]]]
CloseIssue = Callable[[str, int, str], None]
ListOpenDigests = Callable[[str], list[dict[str, Any]]]


def issue_label_names(issue: dict[str, Any] | None) -> set[str]:
    """Normalize GitHub label list / strings to a lower-case set."""
    if not isinstance(issue, dict):
        return set()
    raw = issue.get("labels")
    out: set[str] = set()
    if isinstance(raw, str):
        for part in raw.split(","):
            s = part.strip().lower()
            if s:
                out.add(s)
        return out
    if not isinstance(raw, (list, tuple)):
        return out
    for item in raw:
        if isinstance(item, str):
            s = item.strip().lower()
        elif isinstance(item, dict):
            s = str(item.get("name") or "").strip().lower()
        else:
            s = str(item or "").strip().lower()
        if s:
            out.add(s)
    return out


def is_fr_digest_issue(issue: dict[str, Any] | None) -> bool:
    """True when labels include ``fr-digest`` / ``digest`` (issues only)."""
    return bool(issue_label_names(issue) & DIGEST_LABELS)


def is_held_issue(issue: dict[str, Any] | None) -> bool:
    """True when labels include ``hold`` / ``on-hold``."""
    return bool(issue_label_names(issue) & HOLD_LABELS)


def _canon_repo(repo: str) -> str:
    return str(repo or "").strip()


def _canon_num(num: int | str) -> int:
    s = str(num or "").strip().lstrip("#")
    if not s.isdigit():
        raise ValueError(f"invalid issue number: {num!r}")
    return int(s)


def _issue_state(issue: dict[str, Any] | None) -> str:
    if not isinstance(issue, dict):
        return ""
    return str(issue.get("state") or "").strip().lower()


def close_comment(child_repo: str, child_number: int | str) -> str:
    """Comment body when closing a digest after its last child."""
    repo = _canon_repo(child_repo)
    num = _canon_num(child_number)
    shown = f"{repo}#{num}" if repo else f"#{num}"
    return (
        f"Last open child {shown} closed. Closing fr-digest as batch complete "
        f"(FR #9552)."
    )


def _filter_exclude(
    issues: Iterable[dict[str, Any]],
    *,
    exclude_nums: set[int],
) -> list[dict[str, Any]]:
    """Drop issues whose number is in ``exclude_nums`` (just-closed child)."""
    out: list[dict[str, Any]] = []
    for raw in issues:
        if not isinstance(raw, dict):
            continue
        try:
            num = int(str(raw.get("number") or "").strip().lstrip("#"))
        except ValueError:
            continue
        if num in exclude_nums:
            continue
        out.append(raw)
    return out


def maybe_close_one_digest(
    digest_repo: str,
    digest_number: int | str,
    *,
    last_child_repo: str = "",
    last_child_number: int | str | None = None,
    fetch_issue: FetchIssue | None = None,
    list_open_issues: ListOpenIssues | None = None,
    close_issue: CloseIssue | None = None,
    digest_issue: dict[str, Any] | None = None,
    open_issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Close one digest when it is an unheld fr-digest with no open children left.

    Returns a result dict with ``action`` in
    ``closed|skipped_not_digest|skipped_held|skipped_already_closed|
    skipped_open_children|skipped_missing|error``.
    """
    repo = _canon_repo(digest_repo)
    try:
        num = _canon_num(digest_number)
    except ValueError as exc:
        return {
            "repo": repo,
            "number": digest_number,
            "action": "error",
            "reason": str(exc),
        }
    issue = digest_issue
    if issue is None and fetch_issue is not None:
        try:
            issue = fetch_issue(repo, num)
        except Exception as exc:  # noqa: BLE001
            return {
                "repo": repo,
                "number": num,
                "action": "error",
                "reason": f"fetch:{type(exc).__name__}",
            }
    if not isinstance(issue, dict):
        return {
            "repo": repo,
            "number": num,
            "action": "skipped_missing",
            "reason": "digest not found",
        }
    if _issue_state(issue) in ("closed", "close"):
        return {
            "repo": repo,
            "number": num,
            "action": "skipped_already_closed",
            "reason": "already closed",
        }
    if not is_fr_digest_issue(issue):
        return {
            "repo": repo,
            "number": num,
            "action": "skipped_not_digest",
            "reason": "no fr-digest/digest label",
        }
    if is_held_issue(issue):
        return {
            "repo": repo,
            "number": num,
            "action": "skipped_held",
            "reason": "hold label present",
        }

    if open_issues is None:
        if list_open_issues is None:
            return {
                "repo": repo,
                "number": num,
                "action": "error",
                "reason": "no list_open_issues",
            }
        try:
            open_issues = list(list_open_issues(repo) or [])
        except Exception as exc:  # noqa: BLE001
            return {
                "repo": repo,
                "number": num,
                "action": "error",
                "reason": f"list:{type(exc).__name__}",
            }

    exclude_nums: set[int] = set()
    if last_child_number is not None:
        try:
            exclude_nums.add(_canon_num(last_child_number))
        except ValueError:
            pass
    candidates = _filter_exclude(open_issues, exclude_nums=exclude_nums)
    children = find_open_children(repo, num, candidates)
    if children:
        ids = [
            f"{_canon_repo(str(c.get('repo') or repo))}#{c.get('number')}"
            for c in children
        ]
        return {
            "repo": repo,
            "number": num,
            "action": "skipped_open_children",
            "reason": "open children remain",
            "children": ids,
        }

    child_repo = _canon_repo(last_child_repo) or repo
    child_num = (
        _canon_num(last_child_number)
        if last_child_number is not None
        else 0
    )
    comment = close_comment(child_repo, child_num) if child_num else (
        "No open Depends-on children remain. Closing fr-digest as batch complete "
        "(FR #9552)."
    )
    if close_issue is None:
        return {
            "repo": repo,
            "number": num,
            "action": "error",
            "reason": "no close_issue",
        }
    try:
        close_issue(repo, num, comment)
    except Exception as exc:  # noqa: BLE001
        return {
            "repo": repo,
            "number": num,
            "action": "error",
            "reason": f"close:{type(exc).__name__}",
        }
    return {
        "repo": repo,
        "number": num,
        "action": "closed",
        "reason": "last child closed",
        "comment": comment,
    }


def maybe_close_fr_digest_parents(
    *,
    child_repo: str,
    child_number: int | str,
    child_body: str | None,
    fetch_issue: FetchIssue,
    list_open_issues: ListOpenIssues,
    close_issue: CloseIssue,
) -> list[dict[str, Any]]:
    """On child close: close each Depends-on parent that is an unheld fr-digest."""
    home = _canon_repo(child_repo)
    try:
        cnum = _canon_num(child_number)
    except ValueError:
        return []
    refs = parse_depends_on(child_body, repo=home)
    if not refs:
        return []
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    # Reuse one open-issue list per repo within this call.
    open_cache: dict[str, list[dict[str, Any]]] = {}

    def _cached_open(repo: str) -> list[dict[str, Any]]:
        key = repo.lower()
        if key not in open_cache:
            open_cache[key] = list(list_open_issues(repo) or [])
        return open_cache[key]

    for pref, pnum in refs:
        repo = _canon_repo(pref) or home
        if not repo:
            continue
        key = (repo.lower(), int(pnum))
        if key in seen:
            continue
        seen.add(key)
        results.append(
            maybe_close_one_digest(
                repo,
                int(pnum),
                last_child_repo=home,
                last_child_number=cnum,
                fetch_issue=fetch_issue,
                list_open_issues=_cached_open,
                close_issue=close_issue,
                open_issues=_cached_open(repo),
            )
        )
    return results


def reconcile_open_fr_digests(
    repo: str,
    *,
    list_open_digest_issues: ListOpenDigests,
    list_open_issues: ListOpenIssues,
    close_issue: CloseIssue,
    fetch_issue: FetchIssue | None = None,
) -> list[dict[str, Any]]:
    """Hourly/resync: close every open unheld fr-digest with zero open children."""
    home = _canon_repo(repo)
    if not home or "/" not in home:
        return []
    try:
        digests = list(list_open_digest_issues(home) or [])
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "repo": home,
                "number": 0,
                "action": "error",
                "reason": f"list_digests:{type(exc).__name__}",
            }
        ]
    try:
        open_issues = list(list_open_issues(home) or [])
    except Exception as exc:  # noqa: BLE001
        return [
            {
                "repo": home,
                "number": 0,
                "action": "error",
                "reason": f"list:{type(exc).__name__}",
            }
        ]
    results: list[dict[str, Any]] = []
    for dig in digests:
        if not isinstance(dig, dict):
            continue
        try:
            num = int(str(dig.get("number") or "").strip().lstrip("#"))
        except ValueError:
            continue
        if num < 1:
            continue
        results.append(
            maybe_close_one_digest(
                home,
                num,
                digest_issue=dig,
                fetch_issue=fetch_issue,
                list_open_issues=lambda _r, _issues=open_issues: _issues,
                close_issue=close_issue,
                open_issues=open_issues,
            )
        )
    return results


def default_fetch_issue(repo: str, number: int) -> dict[str, Any] | None:
    """Production GET via gitclaim.fetch_github_issue_dict."""
    try:
        import gitclaim

        return gitclaim.fetch_github_issue_dict(repo, str(number))
    except Exception:
        return None


def default_list_open_issues(repo: str) -> list[dict[str, Any]]:
    """Production open-issue list via open_children_gate (path-loaded)."""
    name = "bobiverse_open_children_gate"
    cached = sys.modules.get(name)
    if cached is None or not hasattr(cached, "fetch_open_issues"):
        path = Path(__file__).resolve().with_name("open_children_gate.py")
        # Pre-bind common depends_on so open_children_gate import succeeds
        # even when monitor/depends_on.py already shadows the name (FR #9540).
        sys.modules["depends_on"] = _load_common_depends_on()
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load open_children_gate from {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules[name] = mod
        cached = mod
    return cached.fetch_open_issues(repo)


def default_list_open_digest_issues(repo: str) -> list[dict[str, Any]]:
    """Open issues carrying ``fr-digest`` (falls back to filtering open issues)."""
    pref = _canon_repo(repo)
    if not pref or "/" not in pref:
        return []
    # Prefer filter of open issues (one list call; avoids label-query auth gaps).
    return [i for i in default_list_open_issues(pref) if is_fr_digest_issue(i)]


def default_close_issue(repo: str, number: int, comment: str) -> None:
    """Production close via gh_filer (comment + close)."""
    import gh_filer

    api = gh_filer.default_filer()
    api.close_issue(repo, int(number), comment=str(comment or ""))


def on_issue_closed(
    repo: str,
    number: int | str,
    body: str | None = None,
    *,
    fetch_issue: FetchIssue | None = None,
    list_open_issues: ListOpenIssues | None = None,
    close_issue: CloseIssue | None = None,
) -> list[dict[str, Any]]:
    """Entry point for webhook / poll / apply-closed: best-effort parent digest close."""
    home = _canon_repo(repo)
    if not home or "/" not in home:
        return []
    try:
        cnum = _canon_num(number)
    except ValueError:
        return []
    child_body = body
    fetch = fetch_issue or default_fetch_issue
    if child_body is None:
        issue = fetch(home, cnum)
        if isinstance(issue, dict):
            child_body = str(issue.get("body") or "")
        else:
            child_body = ""
    return maybe_close_fr_digest_parents(
        child_repo=home,
        child_number=cnum,
        child_body=child_body,
        fetch_issue=fetch,
        list_open_issues=list_open_issues or default_list_open_issues,
        close_issue=close_issue or default_close_issue,
    )


def reconcile_repo(
    repo: str,
    *,
    list_open_digest_issues: ListOpenDigests | None = None,
    list_open_issues: ListOpenIssues | None = None,
    close_issue: CloseIssue | None = None,
    fetch_issue: FetchIssue | None = None,
) -> list[dict[str, Any]]:
    """Entry point for hourly ticket-closure / github-resync reconcile."""
    return reconcile_open_fr_digests(
        repo,
        list_open_digest_issues=list_open_digest_issues or default_list_open_digest_issues,
        list_open_issues=list_open_issues or default_list_open_issues,
        close_issue=close_issue or default_close_issue,
        fetch_issue=fetch_issue or default_fetch_issue,
    )
