"""Shared GitHub topic ``priority-customer`` lookup (FR #4969 Jeeves sort, FR #4970 harvest).

One search per resync (not per offer). Lookup failure keeps the last on-disk set.

FR #7391: the topics cache lives under the Jeeves chair state dir (SYSTEM-owned
``BOB_HOME`` / ``.jeeves``), not under ``BOB_DIGEST_HOME`` (which may deny SYSTEM).
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Callable

import bobreport

TOPIC = "priority-customer"
TOPIC_FILE = "priority-customer-topics.json"
TOPIC_HEALTH_FILE = "priority-customer-topics.health.json"
SEARCH_PATH = "/search/repositories"
log = logging.getLogger("bobiverse.priority_customer")

# Last write failure for tests / !status (path + reason; never secrets).
_last_topics_write: dict = {"ok": True, "path": "", "error": ""}


def topics_state_dir(home: Path) -> Path:
    """FR #7391: Jeeves chair state dir SYSTEM owns (not fleet digest root)."""
    p = Path(home)
    if bobreport._is_chair_home(p):
        return p
    bob = (os.environ.get("BOB_HOME") or "").strip()
    if bob:
        try:
            return Path(bob).expanduser()
        except OSError:
            pass
    # pytest / harvest callers that pass a tmp dir: write there (no digest redirect).
    return p


def topics_cache_path(home: Path) -> Path:
    return topics_state_dir(home) / TOPIC_FILE


def topics_health_path(home: Path) -> Path:
    return topics_state_dir(home) / TOPIC_HEALTH_FILE


def last_topics_write_status() -> dict:
    """Copy of last save outcome (no secrets). FR #7391."""
    return dict(_last_topics_write)


def _legacy_digest_topics_path(home: Path) -> Path:
    """Pre-#7391 location under fleet digest home (read fallback only)."""
    return bobreport.fleet_digest_home(Path(home)) / TOPIC_FILE


def github_topic_fetch(url: str) -> object:
    """GET GitHub JSON (topic search). Token from GH_TOKEN / GITHUB_TOKEN when set."""
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


def _read_repos_file(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for r in (raw.get("repos") if isinstance(raw, dict) else None) or []:
        s = str(r or "").strip().lower()
        if s:
            out.add(s)
    return out


def load_topic_repos(home: Path) -> set[str]:
    primary = topics_cache_path(home)
    got = _read_repos_file(primary)
    if got:
        return got
    # Migrate/read last set from pre-#7391 digest location once.
    legacy = _legacy_digest_topics_path(home)
    if legacy != primary:
        return _read_repos_file(legacy)
    return set()


def _write_health(home: Path, *, ok: bool, path: str, error: str = "") -> None:
    global _last_topics_write
    doc = {
        "ok": bool(ok),
        "path": str(path or ""),
        "error": str(error or "")[:200],
    }
    _last_topics_write = dict(doc)
    hp = topics_health_path(home)
    try:
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    except OSError:
        pass
    with contextlib.suppress(Exception):
        publish_topics_health_warning(home, doc)


def publish_topics_health_warning(home: Path, status: dict | None = None) -> None:
    """FR #7391: mirror topics-cache health onto the fleet digest (no secrets)."""
    st = dict(status) if isinstance(status, dict) else last_topics_write_status()
    try:
        root = bobreport.fleet_digest_home(Path(home))
        doc = bobreport.load_digest(root)
        health = dict(doc.get("health") or {}) if isinstance(doc.get("health"), dict) else {}
        if st.get("ok"):
            health.pop("priority_customer_topics", None)
        else:
            health["priority_customer_topics"] = {
                "ok": False,
                "path": str(st.get("path") or ""),
                "error": str(st.get("error") or "")[:200],
            }
        if health:
            doc["health"] = health
        else:
            doc.pop("health", None)
        bobreport.save_digest(root, doc)
    except Exception:  # noqa: BLE001 - never fail refresh on digest health paint
        pass


_REPLACE_ATTEMPTS = 5
_REPLACE_BACKOFF_S = 0.05


def _locked_replace(exc: BaseException) -> bool:
    """Windows access-denied / sharing violation, or POSIX EACCES/EPERM."""
    win = getattr(exc, "winerror", None)
    if win in (5, 32, 33):
        return True
    return getattr(exc, "errno", None) in (13, 1)


def _cleanup_stale_topic_tmps(dest: Path, keep: Path | None = None) -> None:
    """Drop leftover ``<file>.*.tmp`` from a crashed writer. Never touches ``dest``."""
    try:
        parent = dest.parent
        prefix = dest.name + "."
        for old in parent.glob(prefix + "*.tmp"):
            if keep is not None and old == keep:
                continue
            with contextlib.suppress(OSError):
                old.unlink()
    except OSError:
        return


def _replace_retry(tmp: Path, dest: Path) -> None:
    """FR #7518: retry os.replace when the destination is briefly locked."""
    last: OSError | None = None
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, dest)
            return
        except OSError as exc:
            last = exc
            if not _locked_replace(exc) or attempt + 1 >= _REPLACE_ATTEMPTS:
                raise
            time.sleep(_REPLACE_BACKOFF_S * (attempt + 1))
    if last is not None:
        raise last


def _report_topics_replace_failure(dest: Path, exc: BaseException) -> None:
    """One exception report. Never include file contents."""
    try:
        import crash_report

        crash_report.report_exception(
            "priority-customer-topics",
            type(exc),
            exc,
            None,
        )
    except Exception:
        log.warning(
            "priority-customer topics replace report failed path=%s",
            dest,
        )


def save_topic_repos(home: Path, repos) -> None:
    """Atomic write under chair state dir. Cleans up ``.tmp`` on failure. FR #7391 / #7518."""
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
    dest = topics_cache_path(home)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _write_health(home, ok=False, path=str(dest), error=f"mkdir: {exc}")
        log.warning(
            "priority-customer topics cache mkdir failed path=%s err=%s",
            dest,
            exc,
        )
        raise
    _cleanup_stale_topic_tmps(dest)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    payload = json.dumps({"v": 1, "repos": names}, indent=1, sort_keys=True) + "\n"
    try:
        tmp.write_text(payload, encoding="utf-8")
        _replace_retry(tmp, dest)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        _write_health(home, ok=False, path=str(dest), error=str(exc))
        log.warning(
            "priority-customer topics cache write failed path=%s err=%s; keeping last set",
            dest,
            exc,
        )
        _report_topics_replace_failure(dest, exc)
        raise
    else:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        _write_health(home, ok=True, path=str(dest), error="")


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
    """One GitHub search. On HTTP/timeout/budget/write error: WARN and keep last set."""
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
        try:
            save_topic_repos(home, names)
        except OSError:
            return last
        return load_topic_repos(home)
    except Exception as exc:  # noqa: BLE001 - keep last set (acceptance 4)
        log.warning("priority-customer topic lookup failed; keeping last set: %s", exc)
        return last
