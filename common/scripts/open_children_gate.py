#!/usr/bin/env python3
"""CI-G1 / FR #8839: fail when open issues still Depends-on a parent FR.

Architecture: ``PR closes #P -> search open issues Depends-on:#P -> fail with list``.

Given parent ``owner/repo#P`` (or a PR that Closes that FR), exit non-zero and
list every **open** issue whose ``Depends-on:`` stamp resolves to that parent.
Silent pass while an open child still Depends-on #P is the fail-when.
When ``--pr`` / ``--pr-json`` supplies Closes parents, children that the same PR
also Closes are excluded (consolidated tip co-close; FR #9858).

FR #9905: soft-allow when #P is a non-digest FR-A that Depends-on an fr-digest
and every open child of #P also Depends-on that same digest (digest-chain
siblings waiting for FR-A to close). Closing an fr-digest itself with open
children still hard-fails.

Reusable for other SimonBarnett repos. CI-G2 wires this into build-jeeves.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

from depends_on import parse_depends_on

try:
    from fr_digest_gate import DIGEST_LABELS, is_digest_filing
except Exception:  # pragma: no cover - offline / thin trees
    DIGEST_LABELS = frozenset({"fr-digest", "digest"})

    def is_digest_filing(*, title: str = "", body: str = "", labels: Iterable[str] | None = None) -> bool:
        labs = {str(x).strip().lower() for x in (labels or ()) if str(x).strip()}
        if labs & DIGEST_LABELS:
            return True
        return "fr-digest" in str(body or "").lower() or str(title or "").lower().startswith("digest:")

# Short TTL for live GitHub issue list lookups (vision UNKNOWN; implementer pick).
OPEN_CHILDREN_CACHE_TTL_S = 60.0
_OPEN_ISSUES_CACHE: dict[str, tuple[float, list[dict]]] = {}

IssueFetcher = Callable[[str], list[dict]]


def _canon_repo(repo: str) -> str:
    return str(repo or "").strip()


def _canon_num(num: int | str) -> int:
    s = str(num or "").strip().lstrip("#")
    if not s.isdigit():
        raise ValueError(f"invalid issue number: {num!r}")
    return int(s)


def child_depends_on_parent(
    body: str | None,
    child_repo: str,
    parent_repo: str,
    parent_num: int | str,
) -> bool:
    """True when a Depends-on stamp on ``body`` resolves to parent_repo#parent_num."""
    pref = _canon_repo(parent_repo)
    pnum = _canon_num(parent_num)
    if not pref:
        return False
    home = _canon_repo(child_repo) or pref
    for repo, num in parse_depends_on(body, repo=home):
        r = _canon_repo(repo) or home
        if r.lower() == pref.lower() and int(num) == pnum:
            return True
    return False


def find_open_children(
    parent_repo: str,
    parent_num: int | str,
    issues: Iterable[dict],
) -> list[dict]:
    """Return open issue dicts that Depends-on ``parent_repo#parent_num``.

    Each issue dict needs ``number``, ``body``, optional ``repository`` /
    ``repo`` / ``html_url``, and optional ``state`` (non-open skipped).
    """
    pref = _canon_repo(parent_repo)
    pnum = _canon_num(parent_num)
    out: list[dict] = []
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
        repo = _issue_repo(raw, default=pref)
        if child_depends_on_parent(raw.get("body"), repo, pref, pnum):
            key = (repo.lower(), num)
            if key in seen:
                continue
            seen.add(key)
            row = dict(raw)
            row.setdefault("repo", repo)
            out.append(row)
    out.sort(key=lambda r: (str(r.get("repo") or ""), int(r.get("number") or 0)))
    return out


def _issue_repo(issue: dict, *, default: str = "") -> str:
    for key in ("repo", "repository"):
        v = issue.get(key)
        if isinstance(v, str) and "/" in v.strip():
            return v.strip()
        if isinstance(v, dict):
            full = str(v.get("full_name") or "").strip()
            if full:
                return full
            owner = v.get("owner")
            name = str(v.get("name") or "").strip()
            if isinstance(owner, dict):
                login = str(owner.get("login") or "").strip()
            else:
                login = str(owner or "").strip()
            if login and name:
                return f"{login}/{name}"
    url = str(issue.get("html_url") or issue.get("url") or "")
    # https://github.com/owner/repo/issues/N
    parts = url.replace("https://api.github.com/repos/", "").replace(
        "https://github.com/", ""
    ).split("/")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[0]}/{parts[1]}"
    return _canon_repo(default)


def format_open_children_report(
    parent_repo: str,
    parent_num: int | str,
    children: list[dict],
) -> list[str]:
    pref = _canon_repo(parent_repo)
    pnum = _canon_num(parent_num)
    lines = [
        f"open-children-gate: FAIL {pref}#{pnum} still has "
        f"{len(children)} open Depends-on child(ren):"
    ]
    for ch in children:
        repo = _issue_repo(ch, default=pref)
        num = ch.get("number")
        title = str(ch.get("title") or "").strip()
        url = str(ch.get("html_url") or ch.get("url") or "").strip()
        bit = f"  - {repo}#{num}"
        if title:
            bit += f" {title}"
        if url:
            bit += f" {url}"
        lines.append(bit)
    return lines


def _label_name_list(labels: Any) -> list[str]:
    out: list[str] = []
    if isinstance(labels, str):
        return [p.strip() for p in labels.split(",") if p.strip()]
    if not isinstance(labels, (list, tuple)):
        return out
    for item in labels:
        if isinstance(item, str):
            n = item.strip()
        elif isinstance(item, dict):
            n = str(item.get("name") or "").strip()
        else:
            n = ""
        if n:
            out.append(n)
    return out


def _find_issue(
    issues: Iterable[dict],
    repo: str,
    num: int,
) -> dict | None:
    pref = _canon_repo(repo).lower()
    for raw in issues:
        if not isinstance(raw, dict):
            continue
        try:
            n = int(str(raw.get("number") or "").strip().lstrip("#"))
        except ValueError:
            continue
        if n != num:
            continue
        r = _issue_repo(raw, default=repo).lower()
        if r == pref or not pref:
            return raw
    return None


def _issue_is_digest(issue: dict | None) -> bool:
    if not isinstance(issue, dict):
        return False
    return is_digest_filing(
        title=str(issue.get("title") or ""),
        body=str(issue.get("body") or ""),
        labels=_label_name_list(issue.get("labels")),
    )


def parent_digest_depends(
    parent_repo: str,
    parent_issue: dict,
    issues: Iterable[dict],
) -> list[tuple[str, int]]:
    """Return digest parents that ``parent_issue`` Depends-on (label/Kind/title)."""
    pref = _canon_repo(parent_repo)
    home = _issue_repo(parent_issue, default=pref) or pref
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    issue_list = list(issues)
    for repo, num in parse_depends_on(parent_issue.get("body"), repo=home):
        r = _canon_repo(repo) or home
        key = (r.lower(), int(num))
        if key in seen:
            continue
        dep = _find_issue(issue_list, r, int(num))
        if not _issue_is_digest(dep):
            continue
        seen.add(key)
        out.append((r, int(num)))
    return out


def soft_allow_digest_chain(
    parent_repo: str,
    parent_num: int | str,
    issues: Iterable[dict],
    children: list[dict],
) -> tuple[bool, list[tuple[str, int]]]:
    """FR #9905: True when every open child shares an fr-digest Depends-on with #P.

    Closing an fr-digest itself never soft-allows. Parent must Depends-on at
    least one digest present in ``issues``; each child must Depends-on that
    same digest.
    """
    pref = _canon_repo(parent_repo)
    pnum = _canon_num(parent_num)
    issue_list = list(issues)
    parent = _find_issue(issue_list, pref, pnum)
    if parent is None:
        return False, []
    if _issue_is_digest(parent):
        return False, []
    digests = parent_digest_depends(pref, parent, issue_list)
    if not digests:
        return False, []
    for ch in children:
        ch_repo = _issue_repo(ch, default=pref)
        ok_child = False
        for d_repo, d_num in digests:
            if child_depends_on_parent(ch.get("body"), ch_repo, d_repo, d_num):
                ok_child = True
                break
        if not ok_child:
            return False, digests
    return True, digests


def gate_open_children(
    parent_repo: str,
    parent_num: int | str,
    *,
    issues: Iterable[dict] | None = None,
    fetch_issues: IssueFetcher | None = None,
    exclude_closing: set[tuple[str, int]] | None = None,
) -> tuple[int, list[str]]:
    """Return ``(exit_code, stdout_lines)``. 1 when open children remain.

    ``exclude_closing``: ``(repo_lower, number)`` pairs this PR also Closes.
    Co-closed Depends-on children are ignored so a consolidated tip that Closes
    parent + child can pass CI-G1 (FR #9858 / #8839).
    """
    pref = _canon_repo(parent_repo)
    pnum = _canon_num(parent_num)
    if issues is None:
        getter = fetch_issues or fetch_open_issues
        issues = getter(pref)
    issue_list = list(issues)
    children = find_open_children(pref, pnum, issue_list)
    if exclude_closing:
        kept: list[dict] = []
        for child in children:
            crepo = _issue_repo(child, default=pref).lower()
            try:
                cnum = int(str(child.get("number") or "").strip().lstrip("#"))
            except ValueError:
                kept.append(child)
                continue
            if (crepo, cnum) in exclude_closing:
                continue
            kept.append(child)
        children = kept
    if not children:
        return 0, [f"open-children-gate: ok {pref}#{pnum} (no open Depends-on children)"]
    allow, digests = soft_allow_digest_chain(pref, pnum, issue_list, children)
    if allow:
        digest_bits = ", ".join(f"{r}#{n}" for r, n in digests) or "digest"
        return 0, [
            f"open-children-gate: ok {pref}#{pnum} soft-allow digest-chain "
            f"({len(children)} open child(ren) share {digest_bits}; FR #9905)"
        ]
    return 1, format_open_children_report(pref, pnum, children)

def _github_token(token: str = "") -> str:
    tok = (
        token
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    ).strip()
    if tok:
        return tok
    try:
        import gh_filer

        gh_filer.ensure_gh_token_env()
        return (
            os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        ).strip()
    except Exception:
        return ""


def _github_get_json(url: str, *, token: str = "") -> Any:
    tok = _github_token(token)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-open-children-gate",
            **({"Authorization": f"Bearer {tok}"} if tok else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_open_issues(repo: str, *, token: str = "") -> list[dict]:
    """List open issues for ``repo`` via GitHub REST (cached ``OPEN_CHILDREN_CACHE_TTL_S``)."""
    pref = _canon_repo(repo)
    if not pref or "/" not in pref:
        return []
    now = time.monotonic()
    hit = _OPEN_ISSUES_CACHE.get(pref.lower())
    if hit is not None and (now - hit[0]) < OPEN_CHILDREN_CACHE_TTL_S:
        return list(hit[1])
    issues: list[dict] = []
    page = 1
    while page <= 20:
        q = urllib.parse.urlencode(
            {"state": "open", "per_page": "100", "page": str(page)}
        )
        api = f"https://api.github.com/repos/{pref}/issues?{q}"
        try:
            batch = _github_get_json(api, token=token)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
            break
        if not isinstance(batch, list) or not batch:
            break
        for item in batch:
            if not isinstance(item, dict):
                continue
            # Issues API includes PRs; skip pull_request keys.
            if "pull_request" in item:
                continue
            item = dict(item)
            item.setdefault("repo", pref)
            issues.append(item)
        if len(batch) < 100:
            break
        page += 1
    _OPEN_ISSUES_CACHE[pref.lower()] = (now, list(issues))
    return issues


def fetch_pr_dict(repo: str, pr_num: int | str, *, token: str = "") -> dict | None:
    """GET pull ``repo#pr_num`` including body (Closes lines). CI-G2 live ``--pr``."""
    pref = _canon_repo(repo)
    num = _canon_num(pr_num)
    if not pref:
        return None
    api = f"https://api.github.com/repos/{pref}/pulls/{num}"
    try:
        data = _github_get_json(api, token=token)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def parents_from_pr_closing_refs(pr: dict, default_repo: str = "") -> list[tuple[str, int]]:
    """Extract ``(repo, num)`` parents from a PR ``closingIssuesReferences`` or body Closes."""
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    home = _canon_repo(default_repo) or _issue_repo(pr, default="")
    refs = pr.get("closingIssuesReferences") or pr.get("closing_issues") or []
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            try:
                num = int(ref.get("number"))
            except (TypeError, ValueError):
                continue
            repo = ""
            r = ref.get("repository")
            if isinstance(r, dict):
                owner = r.get("owner")
                name = str(r.get("name") or "").strip()
                login = (
                    str(owner.get("login") or "").strip()
                    if isinstance(owner, dict)
                    else str(owner or "").strip()
                )
                if login and name:
                    repo = f"{login}/{name}"
            repo = repo or home
            if not repo:
                continue
            key = (repo.lower(), num)
            if key in seen:
                continue
            seen.add(key)
            out.append((repo, num))
    if out:
        return out
    # Fallback: Closes owner/repo#N / Closes #N in body
    import re

    body = str(pr.get("body") or "")
    for m in re.finditer(
        r"(?im)\b(?:Closes|Close|Fixes|Fix|Resolves|Resolve)\s+:?\s*"
        r"(?:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?\#(\d+)",
        body,
    ):
        repo = (m.group(1) or home).strip()
        num = int(m.group(2))
        if not repo:
            continue
        key = (repo.lower(), num)
        if key in seen:
            continue
        seen.add(key)
        out.append((repo, num))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="CI-G1 / FR #8839: fail when open issues Depends-on parent FR"
    )
    p.add_argument("--repo", required=True, help="owner/name (e.g. SimonBarnett/bobiverse)")
    p.add_argument(
        "--parent",
        type=str,
        default="",
        help="Parent FR number (with or without #). Repeat via comma list.",
    )
    p.add_argument(
        "--pr",
        type=str,
        default="",
        help="Optional PR number: derive parents from Closes / closingIssuesReferences JSON.",
    )
    p.add_argument(
        "--issues-json",
        type=str,
        default="",
        help="Offline: path to JSON list of issue dicts (skips GitHub fetch).",
    )
    p.add_argument(
        "--pr-json",
        type=str,
        default="",
        help="Offline: path to PR JSON for --pr parent derivation.",
    )
    args = p.parse_args(argv)
    repo = _canon_repo(args.repo)
    issues: list[dict] | None = None
    if args.issues_json:
        with open(args.issues_json, encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, list):
            print("open-children-gate: --issues-json must be a JSON list", file=sys.stderr)
            return 2
        issues = raw

    parents: list[tuple[str, int]] = []
    if args.parent:
        for part in str(args.parent).split(","):
            part = part.strip()
            if not part:
                continue
            parents.append((repo, _canon_num(part)))
    pr_mode = bool(args.pr or args.pr_json)
    if pr_mode:
        pr_obj: dict[str, Any]
        if args.pr_json:
            with open(args.pr_json, encoding="utf-8") as fh:
                pr_obj = json.load(fh)
            if not isinstance(pr_obj, dict):
                print("open-children-gate: --pr-json must be a JSON object", file=sys.stderr)
                return 2
        else:
            fetched = fetch_pr_dict(repo, args.pr)
            if not isinstance(fetched, dict):
                print(
                    f"open-children-gate: failed to fetch PR {repo}#{args.pr}",
                    file=sys.stderr,
                )
                return 2
            pr_obj = fetched
        parents.extend(parents_from_pr_closing_refs(pr_obj, default_repo=repo))

    # Dedupe parents
    uniq: list[tuple[str, int]] = []
    seen_p: set[tuple[str, int]] = set()
    for r, n in parents:
        key = (r.lower(), n)
        if key in seen_p:
            continue
        seen_p.add(key)
        uniq.append((r, n))
    if not uniq:
        if pr_mode:
            # PR with no Closes parents: nothing to gate (soft-ok for CI-G2).
            print(
                f"open-children-gate: ok {repo} PR has no Closes parents "
                "(nothing to check)"
            )
            return 0
        print(
            "open-children-gate: need --parent N and/or --pr / --pr-json",
            file=sys.stderr,
        )
        return 2

    # Same-PR co-close: children this tip also Closes are not blockers (CI-G1).
    exclude: set[tuple[str, int]] | None = None
    if pr_mode:
        exclude = {(r.lower(), n) for r, n in uniq}

    exit_code = 0
    for pref, pnum in uniq:
        code, lines = gate_open_children(
            pref, pnum, issues=issues, exclude_closing=exclude
        )
        for line in lines:
            print(line)
        if code != 0:
            exit_code = code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
