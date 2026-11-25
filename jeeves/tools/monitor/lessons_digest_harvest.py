#!/usr/bin/env python3
"""Active held fr-digest lessons harvest checklist (FR #9880).

Checklist id ``9830_harvest`` (alias): while an OPEN+held *lessons* fr-digest
exists, every MONITORING cycle that learns a Jeeves/IRCD/ear/webhook lesson
must same-turn file a child FR (``Depends-on: #<digest>``) or de-dup-comment.

This token-free helper:
* resolves the active held lessons digest (detection, env, or documented default)
* lists open children that Depends-on that digest
* optionally diffs session findings vs those children (EXIT 1 when unfiled)

Do **not** hardcode forever that only #9830 exists. Prefer:
1. ``JEEVES_LESSONS_DIGEST_FIXTURE`` JSON (tests / offline)
2. ``JEEVES_LESSONS_DIGEST`` / ``BOB_LESSONS_DIGEST`` (``N`` or ``owner/repo#N``)
3. active OPEN+held ``fr-digest`` issues whose title/body look like a lessons digest
4. documented current default ``SimonBarnett/bobiverse#9830`` when still OPEN+held

Env ``JEEVES_LESSONS_SESSION_FINDINGS`` (JSON list) or fixture ``session_findings``
drives the unfiled-finding gate. Without findings the check is informational
(EXIT 0) and still emits digest + children for the agent checklist.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from _common import EXIT_FINDING, EXIT_OK, run_check

CHECK_NAME = "lessons_digest_harvest"
# Documented current default while Digest #9830 is the active lessons batch.
DEFAULT_REPO = "SimonBarnett/bobiverse"
DEFAULT_DIGEST_NUMBER = 9830

_DEPENDS_LINE = re.compile(
    r"(?im)^[^\S\n]*"
    r"(?:\*{0,2}|`{0,2})"
    r"Depends-on"
    r"(?:\*{0,2}|`{0,2})"
    r"[^\S\n]*:"
    r"(?:\*{0,2}|`{0,2})?"
    r"[^\S\n]*(.*)$"
)
_REF = re.compile(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)|#(\d+)")
_NONE = re.compile(r"^\(?none\)?$|^-$", re.I)
_LESSONS_CUE = re.compile(
    r"(?i)\b(lesson|lessons|ircd|jeeves.?ircd|ear|webhook|monitoring)\b"
)
_DIGEST_TITLE = re.compile(r"(?i)^\s*digest\b")


def _label_names(labels: Any) -> set[str]:
    names: set[str] = set()
    raw = labels or []
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, list):
        return names
    for item in raw:
        if isinstance(item, str):
            names.add(item.strip().lower())
        elif isinstance(item, dict):
            names.add(str(item.get("name") or "").strip().lower())
    return names


def is_held_fr_digest(issue: dict) -> bool:
    names = _label_names(issue.get("labels"))
    if "hold" not in names and "on-hold" not in names:
        return False
    if "fr-digest" in names or "digest" in names:
        return True
    title = str(issue.get("title") or "")
    return bool(_DIGEST_TITLE.match(title))


def looks_like_lessons_digest(issue: dict) -> bool:
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    if _LESSONS_CUE.search(title):
        return True
    if _LESSONS_CUE.search(body[:2000]):
        return True
    # Explicit CAST IRON harvest-onto-digest cue from #9880 family.
    if re.search(r"(?i)every monitor.*(file|harvest).*lesson", body):
        return True
    return False


def parse_digest_spec(raw: str, default_repo: str = DEFAULT_REPO) -> tuple[str, int] | None:
    text = (raw or "").strip()
    if not text:
        return None
    m = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)", text)
    if m:
        return m.group(1), int(m.group(2))
    m = re.fullmatch(r"#?(\d+)", text)
    if m:
        return default_repo, int(m.group(1))
    return None


def env_digest_override(env: dict | None = None) -> tuple[str, int] | None:
    env = os.environ if env is None else env
    for key in ("JEEVES_LESSONS_DIGEST", "BOB_LESSONS_DIGEST"):
        parsed = parse_digest_spec(str(env.get(key) or ""))
        if parsed:
            return parsed
    return None


def documented_default_digest() -> tuple[str, int]:
    return DEFAULT_REPO, DEFAULT_DIGEST_NUMBER


def issue_number(issue: dict) -> int | None:
    raw = issue.get("number")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def issue_repo(issue: dict, default_repo: str = DEFAULT_REPO) -> str:
    repo = str(issue.get("repo") or issue.get("repository") or "").strip()
    if repo:
        return repo
    # gh issue json sometimes nests repository.full_name
    nested = issue.get("repository")
    if isinstance(nested, dict):
        full = str(nested.get("full_name") or "").strip()
        if full:
            return full
    return default_repo


def issue_is_open(issue: dict) -> bool:
    state = str(issue.get("state") or "OPEN").strip().upper()
    return state in ("OPEN", "OPENED", "")


def depends_on_digest(body: str, repo: str, number: int, default_repo: str) -> bool:
    for line in _DEPENDS_LINE.findall(body or ""):
        text = line.strip().strip("`*")
        if not text or _NONE.match(text):
            continue
        for match in _REF.finditer(text):
            if match.group(1):
                if match.group(1).lower() == repo.lower() and int(match.group(2)) == number:
                    return True
            elif default_repo.lower() == repo.lower() and int(match.group(3)) == number:
                return True
    return False


def normalize_finding_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def finding_covered(finding: dict, children: list[dict]) -> bool:
    keys: list[str] = []
    for field in ("fingerprint", "title", "body", "id"):
        val = finding.get(field)
        if val:
            keys.append(normalize_finding_key(str(val)))
    keys = [k for k in keys if k]
    if not keys:
        return False
    for child in children:
        blob = normalize_finding_key(
            " ".join(
                str(child.get(x) or "")
                for x in ("title", "body", "fingerprint", "number")
            )
        )
        for key in keys:
            if key and key in blob:
                return True
    return False


def pick_active_held_lessons_digest(
    issues: list[dict],
    *,
    override: tuple[str, int] | None = None,
    default: tuple[str, int] | None = None,
) -> dict | None:
    """Prefer override if OPEN+held; else newest lessons-cue held digest; else default if active."""
    open_held = [i for i in issues if isinstance(i, dict) and issue_is_open(i) and is_held_fr_digest(i)]
    if override:
        orepo, onum = override
        for issue in open_held:
            if issue_number(issue) == onum and issue_repo(issue, orepo).lower() == orepo.lower():
                return issue
    lessons = [i for i in open_held if looks_like_lessons_digest(i)]
    if lessons:
        lessons.sort(key=lambda i: issue_number(i) or 0, reverse=True)
        return lessons[0]
    if default:
        drepo, dnum = default
        for issue in open_held:
            if issue_number(issue) == dnum and issue_repo(issue, drepo).lower() == drepo.lower():
                return issue
    return None


def load_json_path(path: str | Path) -> Any:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8-sig"))


def load_fixture(env: dict | None = None) -> dict | None:
    env = os.environ if env is None else env
    raw = (env.get("JEEVES_LESSONS_DIGEST_FIXTURE") or "").strip()
    if not raw:
        return None
    data = load_json_path(raw)
    if not isinstance(data, dict):
        raise ValueError("JEEVES_LESSONS_DIGEST_FIXTURE must be a JSON object")
    return data


def load_session_findings(env: dict | None = None, fixture: dict | None = None) -> list[dict]:
    env = os.environ if env is None else env
    if fixture and isinstance(fixture.get("session_findings"), list):
        return [x for x in fixture["session_findings"] if isinstance(x, dict)]
    raw = (env.get("JEEVES_LESSONS_SESSION_FINDINGS") or "").strip()
    if not raw:
        return []
    data = load_json_path(raw)
    if isinstance(data, dict) and isinstance(data.get("session_findings"), list):
        data = data["session_findings"]
    if not isinstance(data, list):
        raise ValueError("JEEVES_LESSONS_SESSION_FINDINGS must be a JSON list")
    return [x for x in data if isinstance(x, dict)]


def _gh_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "bobiverse-lessons-digest-harvest",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_open_held_fr_digests(repo: str, token: str) -> list[dict]:
    """List open issues with label fr-digest (caller filters hold + lessons)."""
    owner, name = repo.split("/", 1)
    url = (
        f"https://api.github.com/repos/{owner}/{name}/issues"
        f"?state=open&labels=fr-digest&per_page=50"
    )
    req = urllib.request.Request(url, headers=_gh_headers(token))
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out: list[dict] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        if item.get("pull_request"):
            continue
        item = dict(item)
        item.setdefault("repo", repo)
        out.append(item)
    return out


def fetch_open_children(repo: str, digest_number: int, token: str) -> list[dict]:
    """Search open issues that mention Depends-on the digest; filter precisely."""
    owner, name = repo.split("/", 1)
    q = f'repo:{repo} is:issue is:open "Depends-on: #{digest_number}"'
    url = "https://api.github.com/search/issues?q=" + urllib.request.quote(q) + "&per_page=50"
    req = urllib.request.Request(url, headers=_gh_headers(token))
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else None
    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict) or item.get("pull_request"):
            continue
        num = issue_number(item)
        if num == digest_number:
            continue
        body = str(item.get("body") or "")
        if depends_on_digest(body, repo, digest_number, repo):
            row = dict(item)
            row.setdefault("repo", repo)
            out.append(row)
    # Search API may miss bold Depends-on; also scan recent open FRs lightly via issues list.
    # Keep small: if search returned some, trust it; else fall back to label feature-request page.
    if out:
        return out
    url2 = (
        f"https://api.github.com/repos/{owner}/{name}/issues"
        f"?state=open&labels=feature-request&per_page=50"
    )
    req2 = urllib.request.Request(url2, headers=_gh_headers(token))
    with urllib.request.urlopen(req2, timeout=30) as resp2:
        data2 = json.loads(resp2.read().decode("utf-8"))
    for item in data2 or []:
        if not isinstance(item, dict) or item.get("pull_request"):
            continue
        num = issue_number(item)
        if num == digest_number:
            continue
        body = str(item.get("body") or "")
        if depends_on_digest(body, repo, digest_number, repo):
            row = dict(item)
            row.setdefault("repo", repo)
            out.append(row)
    return out


def summarize_issue(issue: dict) -> dict[str, Any]:
    num = issue_number(issue)
    return {
        "repo": issue_repo(issue),
        "number": num,
        "title": str(issue.get("title") or ""),
        "labels": sorted(_label_names(issue.get("labels"))),
        "url": str(issue.get("html_url") or issue.get("url") or ""),
    }


def check(args):
    env = os.environ
    fixture = load_fixture(env)
    override = env_digest_override(env)
    default = documented_default_digest()
    findings = load_session_findings(env, fixture)

    digest_issue: dict | None = None
    children: list[dict] = []
    source = "none"

    if fixture is not None:
        source = "fixture"
        issues = []
        dig = fixture.get("digest")
        if isinstance(dig, dict):
            issues.append(dig)
        extra = fixture.get("issues")
        if isinstance(extra, list):
            issues.extend(x for x in extra if isinstance(x, dict))
        digest_issue = pick_active_held_lessons_digest(
            issues, override=override, default=default if dig is None else None
        )
        if digest_issue is None and isinstance(dig, dict) and issue_is_open(dig) and is_held_fr_digest(dig):
            # Fixture digest present but failed lessons-cue / override: still use when held.
            if override is None or (
                issue_number(dig) == override[1]
                and issue_repo(dig, override[0]).lower() == override[0].lower()
            ):
                digest_issue = dig
        raw_children = fixture.get("children") or []
        if isinstance(raw_children, list):
            children = [c for c in raw_children if isinstance(c, dict)]
        if digest_issue is not None:
            repo = issue_repo(digest_issue)
            num = issue_number(digest_issue)
            if num is not None:
                children = [
                    c
                    for c in children
                    if issue_is_open(c)
                    and depends_on_digest(str(c.get("body") or ""), repo, num, repo)
                ] or [
                    c
                    for c in children
                    if issue_is_open(c)
                ]
    else:
        token = (env.get("GH_TOKEN") or env.get("GITHUB_TOKEN") or "").strip()
        repo_for_fetch = (override or default)[0]
        if not token:
            # Informational soft-ok: agent still follows skill checklist.
            return (
                {
                    "ok": True,
                    "soft_ok": "no_fixture_no_token",
                    "checklist": "9830_harvest",
                    "override": (
                        f"{override[0]}#{override[1]}" if override else None
                    ),
                    "documented_default": f"{default[0]}#{default[1]}",
                    "reminder": (
                        "While an OPEN+held lessons fr-digest is active, same-turn "
                        "file child FRs (Depends-on) or de-dup-comment; never leave "
                        "Jeeves/IRCD/ear/webhook lessons only in chat."
                    ),
                    "findings": [],
                },
                EXIT_OK,
            )
        try:
            issues = fetch_open_held_fr_digests(repo_for_fetch, token)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            return (
                {
                    "ok": False,
                    "error": f"digest_list:{type(e).__name__}",
                    "checklist": "9830_harvest",
                    "findings": [str(e)],
                },
                EXIT_OK,  # soft: network blip must not fail the whole monitor cycle hard
            )
        source = "github"
        digest_issue = pick_active_held_lessons_digest(
            issues, override=override, default=default
        )
        if digest_issue is not None:
            repo = issue_repo(digest_issue, repo_for_fetch)
            num = issue_number(digest_issue)
            if num is not None:
                try:
                    children = fetch_open_children(repo, num, token)
                except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
                    children = []
                    source = f"github_digest_ok_children_err:{type(e).__name__}"

    if digest_issue is None:
        return (
            {
                "ok": True,
                "soft_ok": "no_active_held_lessons_digest",
                "checklist": "9830_harvest",
                "source": source,
                "override": f"{override[0]}#{override[1]}" if override else None,
                "documented_default": f"{default[0]}#{default[1]}",
                "children": [],
                "session_findings": len(findings),
                "unfiled": [],
                "findings": [],
            },
            EXIT_OK,
        )

    child_summaries = [summarize_issue(c) for c in children]
    unfiled = [f for f in findings if not finding_covered(f, children)]
    digest_summary = summarize_issue(digest_issue)
    payload: dict[str, Any] = {
        "ok": not unfiled,
        "checklist": "9830_harvest",
        "source": source,
        "active_digest": digest_summary,
        "children": child_summaries,
        "children_count": len(child_summaries),
        "session_findings": len(findings),
        "unfiled": [
            {
                "title": str(f.get("title") or ""),
                "fingerprint": str(f.get("fingerprint") or ""),
            }
            for f in unfiled
        ],
        "reminder": (
            f"File new Jeeves/IRCD/ear/webhook lessons as children of "
            f"{digest_summary.get('repo')}#{digest_summary.get('number')} "
            f"(Depends-on) or de-dup-comment an existing child."
        ),
        "findings": [
            f"unfiled_session_finding:{f.get('title') or f.get('fingerprint') or '?'}"
            for f in unfiled
        ],
    }
    if unfiled:
        return payload, EXIT_FINDING
    return payload, EXIT_OK


def main(argv: list[str] | None = None) -> int:
    return run_check(
        CHECK_NAME,
        "FR #9880 lessons digest harvest (9830_harvest checklist)",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
