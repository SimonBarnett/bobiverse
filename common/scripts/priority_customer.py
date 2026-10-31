"""Shared GitHub topic ``priority-customer`` lookup (FR #4969 Jeeves sort, FR #4970 harvest).

One search per resync (not per offer). Lookup failure keeps the last on-disk set.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable

import bobreport

TOPIC = "priority-customer"
TOPIC_FILE = "priority-customer-topics.json"
SEARCH_PATH = "/search/repositories"
log = logging.getLogger("bobiverse.priority_customer")


def _root(home: Path) -> Path:
    return bobreport.fleet_digest_home(Path(home))


def github_topic_fetch(url: str) -> object:
    """GET GitHub JSON (topic search). Token from GH_TOKEN / GITHUB_TOKEN when set."""
    import json
    import urllib.request

    hdrs = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "bobiverse-intake",
    }
    tok = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if tok:
        hdrs["Authorization"] = "Bearer " + tok
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def topic_search_url() -> str:
    owner = (os.environ.get("JEEVES_GITHUB_OWNER") or "SimonBarnett").strip() or "SimonBarnett"
    q = f"user:{owner}+topic:{TOPIC}"
    return f"https://api.github.com{SEARCH_PATH}?q={q}&per_page=100"


def load_topic_repos(home: Path) -> set[str]:
    p = _root(home) / TOPIC_FILE
    if not p.is_file():
        return set()
    try:
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for r in (raw.get("repos") if isinstance(raw, dict) else None) or []:
        s = str(r or "").strip().lower()
        if s:
            out.add(s)
    return out


def save_topic_repos(home: Path, repos) -> None:
    names = []
    seen: set[str] = set()
    for r in repos or []:
        s = str(r or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(s if "/" in s else s)
    dest = _root(home) / TOPIC_FILE
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(
        json.dumps({"v": 1, "repos": names}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, dest)


def is_priority_customer(home: Path, repo: str) -> bool:
    key = str(repo or "").strip().lower()
    if not key:
        return False
    known = load_topic_repos(home)
    if key in known:
        return True
    short = key.rsplit("/", 1)[-1]
    return any(k == short or k.endswith("/" + short) for k in known)


def refresh_topic_repos(home: Path, *, fetch_json: Callable[[str], object]) -> set[str]:
    """One GitHub search. On HTTP/timeout/budget error: WARN and keep last set."""
    last = load_topic_repos(home)
    try:
        body = fetch_json(topic_search_url())
        if body is None:
            raise RuntimeError("empty_topic_search")
        items = body.get("items") if isinstance(body, dict) else body
        if not isinstance(items, list):
            raise RuntimeError("bad_topic_search")
        names = []
        for it in items:
            if isinstance(it, dict):
                full = str(it.get("full_name") or "").strip()
                if full:
                    names.append(full)
        save_topic_repos(home, names)
        return load_topic_repos(home)
    except Exception as exc:  # noqa: BLE001 - keep last set (acceptance 4)
        log.warning("priority-customer topic lookup failed; keeping last set: %s", exc)
        return last
