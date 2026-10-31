"""FR #5317: optional CodeRabbit / Copilot / fleet fuel stages.

Each stage is off by default and never load-bearing. A missing CodeRabbit
review holds an MRB offer only while ``BOB_FUEL_CODERABBIT`` is on and the
wait window has not elapsed; after that the row is offered with
``coderabbit=timeout``. Copilot is never required for a fleet offer.
"""
from __future__ import annotations

import os
import re
from typing import Any, Iterable

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_CR_BOT = re.compile(r"(?i)^coderabbitai(\[bot\])?$")
_CR_CHECK = re.compile(r"(?i)coderabbit")


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
    raw = str(src.get("BOB_CODERABBIT_WAIT_MIN") or "15").strip()
    try:
        mins = float(raw)
    except ValueError:
        mins = 15.0
    if mins < 0:
        mins = 15.0
    return mins * 60.0


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
        if _CR_BOT.match(login) and commit.startswith(want):
            return True
    for chk in checks or []:
        if not isinstance(chk, dict):
            continue
        name = str(chk.get("name") or chk.get("context") or "")
        if not _CR_CHECK.search(name):
            continue
        csha = str(chk.get("head_sha") or chk.get("headSha") or "").strip().lower()
        status = str(chk.get("status") or "").strip().lower()
        if csha.startswith(want) and status in ("", "completed"):
            return True
    return False


def lookup_coderabbit_reviewed(repo: str, num: str, head: str = "") -> bool:
    """Live GitHub lookup. Fail-open as 'not yet' (timeout still offers). No secrets logged."""
    repo_s = str(repo or "").strip()
    num_s = str(num or "").strip().lstrip("#")
    if not repo_s or not num_s.isdigit():
        return False
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return False
    import json
    import urllib.request

    api = f"https://api.github.com/repos/{repo_s}/pulls/{num_s}/reviews"
    req = urllib.request.Request(
        api,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-fuel-chain",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            reviews = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return False
    if not isinstance(reviews, list):
        return False
    want = str(head or "").strip()
    if not want:
        return any(
            isinstance(r, dict)
            and _CR_BOT.match(
                str(((r.get("user") or {}) if isinstance(r.get("user"), dict) else {}).get("login") or "")
            )
            for r in reviews
        )
    return coderabbit_reviewed_head(reviews, [], want)


def mrb_coderabbit_offer(
    row: dict,
    *,
    now: float,
    enabled: bool,
    has_review: bool,
    wait_s: float,
    first_seen: float | None = None,
) -> tuple[bool, str]:
    """Return (hold_offer, stamp). Never load-bearing: timeout and off both offer."""
    if not enabled:
        return False, ""
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
    if age >= float(wait_s):
        return False, "timeout"
    return True, ""


def apply_mrb_coderabbit_gate(row: dict, now: float, *, lookup=None) -> bool:
    """Mutate ``row`` stamps. Return True when the offer must wait.

    FR #5394: prefer stamped ``coderabbit=ready`` (webhook). Live lookup is
    optional and must be the caller's budgeted checker on ``!bored``.
    """
    if not isinstance(row, dict):
        return False
    if str(row.get("task") or "").strip().upper() != "MRB":
        return False
    if not stage_enabled("coderabbit"):
        return False
    if "coderabbit_wait_since" not in row:
        row["coderabbit_wait_since"] = float(now)
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("id") or "").strip().lstrip("#")
    has = False
    if str(row.get("coderabbit") or "").strip().lower() == "ready":
        has = True
    else:
        try:
            if lookup is not None:
                has = bool(lookup(repo, num))
            else:
                has = bool(lookup_coderabbit_reviewed(repo, num, str(row.get("head_sha") or "")))
        except Exception:
            has = False
    hold, tag = mrb_coderabbit_offer(
        row,
        now=now,
        enabled=True,
        has_review=has,
        wait_s=wait_seconds(),
        first_seen=float(row.get("coderabbit_wait_since") or now),
    )
    if tag:
        row["coderabbit"] = tag
    return hold


def assign_suffix(row: dict) -> str:
    tag = str((row or {}).get("coderabbit") or "").strip().lower()
    if tag == "timeout":
        return "coderabbit=timeout"
    return ""
