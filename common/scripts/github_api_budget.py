"""Hourly GitHub REST budget + ETag conditional GETs for chair reconcile (FR #3212).

Webhooks are the source of truth. REST is only for startup / gap / low-cadence
reconcile and rare on-demand checks. 304 replies do not charge the budget.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

# Chair core-bucket share of the shared SimonBarnett 5000/h allowance.
DEFAULT_BUDGET_PER_HOUR = 1000
# Stop non-essential REST when GitHub *core* remaining drops below this floor.
# Search is a separate 30/min bucket (FR #5148): never apply this floor to it.
BACKOFF_FLOOR = 500
# Search is 30/min (FR #5148 / #5341). Wait for reset instead of applying BACKOFF_FLOOR.
SEARCH_BACKOFF_FLOOR = 1
SEARCH_RESOURCES = frozenset({"search", "code_search"})
SEARCH_PATH_MARKERS = ("search",)
# No webhook deliveries for this long (while repos are configured) triggers one reconcile.
WEBHOOK_GAP_S = 900.0

ETAG_STATE = "github-api-etags.json"
BUDGET_STATE = "github-api-budget.json"
LAST_WEBHOOK_STATE = "last-git-webhook.json"

# Sentinel: conditional GET returned 304 / unchanged. Does not charge the budget.
NOT_MODIFIED: object = object()


class NotModified(Exception):
    """Raised by budgeted fetchers when GitHub returns 304 Not Modified."""


def _read_json(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def stamp_git_webhook(home: Path, *, now: float | None = None) -> None:
    """Record last successful git webhook delivery (gap detection, FR #3212)."""
    ts = float(time.time() if now is None else now)
    try:
        _write_json(Path(home) / LAST_WEBHOOK_STATE, {"v": 1, "ts": ts})
    except OSError:
        pass


def last_git_webhook_ts(home: Path) -> float | None:
    doc = _read_json(Path(home) / LAST_WEBHOOK_STATE)
    try:
        ts = float(doc.get("ts"))
    except (TypeError, ValueError):
        return None
    return ts if ts > 0 else None


def webhook_gap_due(home: Path, *, now: float | None = None, gap_s: float = WEBHOOK_GAP_S) -> bool:
    """True when deliveries stopped for ``gap_s`` after at least one stamp.

    Never-stamped homes rely on startup / hourly reconcile — a missing stamp must
    not pull the first resync forward past ``FIRST_RESYNC_DELAY_S``.
    """
    now_f = float(time.time() if now is None else now)
    ts = last_git_webhook_ts(home)
    if ts is None:
        return False
    return (now_f - ts) >= float(gap_s)


def _fmt_reset_local(reset_unix: float | None, *, now: float | None = None) -> str:
    if reset_unix is None:
        return "?"
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(reset_unix)))
    except (OverflowError, OSError, ValueError):
        return "?"


class GithubApiBudget:
    """Process + durable hourly call counter with ETag store and backoff floor."""

    def __init__(
        self,
        home: Path,
        *,
        budget_per_hour: int = DEFAULT_BUDGET_PER_HOUR,
        floor: int = BACKOFF_FLOOR,
        clock: Callable[[], float] = time.time,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.home = Path(home)
        self.budget_per_hour = max(0, int(budget_per_hour))
        self.floor = max(0, int(floor))
        self.clock = clock
        self.log = log or (lambda _s: None)
        self._backoff_logged = False
        self._load()

    def _budget_path(self) -> Path:
        return self.home / BUDGET_STATE

    def _etag_path(self) -> Path:
        return self.home / ETAG_STATE

    def _load(self) -> None:
        doc = _read_json(self._budget_path())
        hour = int(self.clock() // 3600)
        stored_hour = int(doc.get("hour") or -1)
        if stored_hour != hour:
            self.used = 0
            self.hour = hour
            self.rate_remaining: int | None = (
                int(doc["rate_remaining"]) if doc.get("rate_remaining") is not None else None
            )
            self.rate_reset: float | None = (
                float(doc["rate_reset"]) if doc.get("rate_reset") is not None else None
            )
            self.search_rate_remaining: int | None = (
                int(doc["search_rate_remaining"])
                if doc.get("search_rate_remaining") is not None
                else None
            )
            self.search_rate_reset: float | None = (
                float(doc["search_rate_reset"])
                if doc.get("search_rate_reset") is not None
                else None
            )
        else:
            self.used = int(doc.get("used") or 0)
            self.hour = stored_hour
            self.rate_remaining = (
                int(doc["rate_remaining"]) if doc.get("rate_remaining") is not None else None
            )
            self.rate_reset = (
                float(doc["rate_reset"]) if doc.get("rate_reset") is not None else None
            )
            self.search_rate_remaining = (
                int(doc["search_rate_remaining"])
                if doc.get("search_rate_remaining") is not None
                else None
            )
            self.search_rate_reset = (
                float(doc["search_rate_reset"])
                if doc.get("search_rate_reset") is not None
                else None
            )
        self.etags = _read_json(self._etag_path())
        if not isinstance(self.etags, dict):
            self.etags = {}

    def _persist_budget(self) -> None:
        try:
            _write_json(
                self._budget_path(),
                {
                    "v": 1,
                    "hour": self.hour,
                    "used": self.used,
                    "budget": self.budget_per_hour,
                    "rate_remaining": self.rate_remaining,
                    "rate_reset": self.rate_reset,
                    "search_rate_remaining": self.search_rate_remaining,
                    "search_rate_reset": self.search_rate_reset,
                },
            )
        except OSError:
            pass

    def _persist_etags(self) -> None:
        try:
            _write_json(self._etag_path(), dict(self.etags))
        except OSError:
            pass

    def _roll_hour(self) -> None:
        hour = int(self.clock() // 3600)
        if hour != self.hour:
            self.hour = hour
            self.used = 0
            self._backoff_logged = False

    def remaining_budget(self) -> int:
        self._roll_hour()
        return max(0, self.budget_per_hour - self.used)

    def rate_limit_cleared(self) -> bool:
        """True when a prior X-RateLimit-Reset unix time is in the past (FR #4422)."""
        if self.rate_reset is None:
            return False
        try:
            return float(self.clock()) >= float(self.rate_reset)
        except (TypeError, ValueError):
            return False

    def clear_rate_limit_if_reset(self) -> bool:
        """Drop stale rate_remaining after reset so reconcile can retry (FR #4422)."""
        if not self.rate_limit_cleared():
            return False
        self.rate_remaining = None
        self.rate_reset = None
        if self.search_rate_reset is not None:
            try:
                if float(self.clock()) >= float(self.search_rate_reset):
                    self.search_rate_remaining = None
                    self.search_rate_reset = None
            except (TypeError, ValueError):
                pass
        self._backoff_logged = False
        self._persist_budget()
        return True

    def _path_is_search(self, path: str) -> bool:
        p = str(path or "").strip().lower()
        return any(m in p for m in SEARCH_PATH_MARKERS) and "reconcile" not in p

    def search_in_backoff(self) -> bool:
        """True when the search bucket is empty and its reset is still in the future."""
        self._roll_hour()
        self.clear_rate_limit_if_reset()
        if self.search_rate_remaining is None:
            return False
        if self.search_rate_reset is not None:
            try:
                if float(self.clock()) >= float(self.search_rate_reset):
                    return False
            except (TypeError, ValueError):
                pass
        return int(self.search_rate_remaining) < SEARCH_BACKOFF_FLOOR

    def in_backoff(self) -> bool:
        self._roll_hour()
        # FR #4422: after GitHub's reset time, forget the stale remaining=0 floor block.
        self.clear_rate_limit_if_reset()
        if self.remaining_budget() <= 0:
            return True
        if self.rate_remaining is not None and self.rate_remaining < self.floor:
            return True
        return False

    def allow(self, path: str, *, essential: bool = False) -> bool:
        """Whether a REST call may proceed. Startup reconcile may use ``essential=True``."""
        self._roll_hour()
        self.clear_rate_limit_if_reset()
        if essential:
            return self.remaining_budget() > 0 or self.used == 0
        if self.in_backoff():
            self._log_backoff_once(path)
            return False
        # FR #5341: a drained search bucket waits for its own reset; core work continues.
        if self._path_is_search(path) and self.search_in_backoff():
            self._log_backoff_once(path)
            return False
        return True

    def skip_reason(self, path: str = "reconcile") -> str:
        """Human-readable why a non-essential call would be skipped (FR #4422)."""
        self._roll_hour()
        self.clear_rate_limit_if_reset()
        rem = self.rate_remaining if self.rate_remaining is not None else "?"
        reset = _fmt_reset_local(self.rate_reset, now=self.clock())
        if self.remaining_budget() <= 0:
            return (
                f"hourly-budget-exhausted path={path} used={self.used}/{self.budget_per_hour} "
                f"remaining={rem} reset={reset}"
            )
        if self.rate_remaining is not None and self.rate_remaining < self.floor:
            return (
                f"rate-limit-floor path={path} used={self.used}/{self.budget_per_hour} "
                f"remaining={rem} floor={self.floor} reset={reset}"
            )
        if self._path_is_search(path) and self.search_in_backoff():
            srem = self.search_rate_remaining if self.search_rate_remaining is not None else "?"
            sreset = _fmt_reset_local(self.search_rate_reset, now=self.clock())
            return (
                f"search-rate-limit-floor path={path} search_remaining={srem} "
                f"search_floor={SEARCH_BACKOFF_FLOOR} search_reset={sreset}"
            )
        return ""

    def _log_backoff_once(self, path: str) -> None:
        if self._backoff_logged:
            return
        self._backoff_logged = True
        why = self.skip_reason(path) or (
            f"path={path} used={self.used}/{self.budget_per_hour} "
            f"remaining={self.rate_remaining if self.rate_remaining is not None else '?'} "
            f"reset={_fmt_reset_local(self.rate_reset, now=self.clock())}"
        )
        self.log(f"WARN github-api backoff {why}")

    def note_headers(self, hdrs) -> None:
        """Record GitHub rate headers per ``X-RateLimit-Resource`` (FR #5148 / #5341).

        ``rate_remaining`` / the 500 floor are **core** only. Search (30/min)
        remaining of 25 must not block reconcile; search uses SEARCH_BACKOFF_FLOOR.
        """
        if hdrs is None:
            return
        try:
            get = getattr(hdrs, "get", None)
            if not callable(get):
                return
            rem = get("X-RateLimit-Remaining") or get("x-ratelimit-remaining")
            reset = get("X-RateLimit-Reset") or get("x-ratelimit-reset")
            resource = (
                get("X-RateLimit-Resource") or get("x-ratelimit-resource") or "core"
            )
            resource_s = str(resource).strip().lower() or "core"
            if rem is not None and str(rem).strip() != "":
                val = int(rem)
                if resource_s in SEARCH_RESOURCES:
                    self.search_rate_remaining = val
                elif resource_s == "core":
                    self.rate_remaining = val
                # graphql / other buckets: do not overwrite core remaining
            if reset is not None and str(reset).strip() != "":
                rst = float(reset)
                if resource_s in SEARCH_RESOURCES:
                    self.search_rate_reset = rst
                elif resource_s == "core":
                    self.rate_reset = rst
        except (TypeError, ValueError):
            pass

    def charge(self, path: str, *, charged: bool = True) -> None:
        self._roll_hour()
        if charged:
            self.used += 1
        rem = self.rate_remaining if self.rate_remaining is not None else "?"
        self.log(
            f"INFO github-api calls={self.used}/{self.budget_per_hour} path={path} "
            f"remaining={rem} reset={_fmt_reset_local(self.rate_reset, now=self.clock())}"
        )
        self._persist_budget()

    def get_etag(self, url: str) -> str | None:
        key = str(url or "").strip()
        val = self.etags.get(key)
        return str(val) if val else None

    def set_etag(self, url: str, etag: str | None) -> None:
        key = str(url or "").strip()
        if not key:
            return
        if etag:
            self.etags[key] = str(etag)
        else:
            self.etags.pop(key, None)
        self._persist_etags()

    def clear_etags_matching(self, pred) -> int:
        """Drop cached ETags whose URL key matches ``pred(url) -> bool``. Returns count removed."""
        drop = [k for k in list(self.etags.keys()) if pred(str(k))]
        for k in drop:
            self.etags.pop(k, None)
        if drop:
            self._persist_etags()
        return len(drop)

    def status_line(self) -> str:
        self._roll_hour()
        rem = self.rate_remaining if self.rate_remaining is not None else "?"
        return (
            f"github-api: used={self.used}/{self.budget_per_hour} "
            f"X-RateLimit-Remaining={rem} reset={_fmt_reset_local(self.rate_reset, now=self.clock())}"
        )

    def conditional_get(
        self,
        url: str,
        *,
        token: str = "",
        path: str = "reconcile",
        essential: bool = False,
        force_refresh: bool = False,
        timeout: float = 30.0,
        opener: Callable[..., Any] | None = None,
    ) -> Any:
        """GET with If-None-Match. Returns JSON body, or ``NOT_MODIFIED`` on 304.

        304 does not charge the hourly budget. Other successes charge one call.
        ``force_refresh`` (FR #4959) skips If-None-Match so !resync / startup /
        partial-list recovery always sees the current open issues and pulls.
        """
        if not self.allow(path, essential=essential):
            raise RuntimeError(f"github-api backoff path={path}")

        hdrs = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-jeeves",
        }
        if token:
            hdrs["Authorization"] = "Bearer " + token
        etag = None if force_refresh else self.get_etag(url)
        if etag:
            hdrs["If-None-Match"] = etag

        def _default_open(req, timeout=timeout):
            return urllib.request.urlopen(req, timeout=timeout)

        open_fn = opener or _default_open
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        try:
            with open_fn(req, timeout=timeout) as resp:
                self.note_headers(getattr(resp, "headers", None))
                status = int(getattr(resp, "status", 200) or 200)
                if status == 304:
                    self.charge(path, charged=False)
                    return NOT_MODIFIED
                raw = resp.read()
                new_etag = None
                try:
                    get = getattr(resp.headers, "get", None)
                    if callable(get):
                        new_etag = get("ETag") or get("etag")
                except Exception:
                    new_etag = None
                if new_etag:
                    self.set_etag(url, new_etag)
                self.charge(path, charged=True)
                if not raw:
                    return []
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.note_headers(getattr(exc, "headers", None))
            if int(exc.code) == 304:
                self.charge(path, charged=False)
                return NOT_MODIFIED
            if int(exc.code) in (401, 403, 429) or int(exc.code) >= 500:
                self._log_backoff_once(path)
            self.charge(path, charged=True)
            raise
        except Exception:
            self.charge(path, charged=True)
            raise


def make_budgeted_fetch(
    budget: GithubApiBudget,
    token: str,
    *,
    path: str = "reconcile",
    essential: bool = False,
    force_refresh: bool = False,
    opener: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """``fetch_json(url)`` seam for resync: raises ``NotModified`` on 304.

    FR #4959: ``force_refresh=True`` (or per-call ``force_refresh=True``) skips
    If-None-Match. Startup / ``!resync`` use this so a stale issues ETag cannot
    hide new open pulls.
    """
    default_force = bool(force_refresh)

    def fetch(url: str, force_refresh: bool = False):
        out = budget.conditional_get(
            url,
            token=token,
            path=path,
            essential=essential,
            force_refresh=bool(force_refresh or default_force),
            opener=opener,
        )
        if out is NOT_MODIFIED:
            raise NotModified(url)
        return out

    return fetch


def invalidate_repo_list_etags(home: Path, repo: str) -> int:
    """Drop cached ETags for open issues/pulls list URLs of ``owner/name`` (FR #4959).

    Webhook ``pull_request`` / ``issues`` deliveries call this so the next reconcile
    re-GETs lists even when the webhook enqueue path missed a row.
    """
    repo_s = str(repo or "").strip()
    if not repo_s or "/" not in repo_s:
        return 0
    needle = f"/repos/{repo_s.lower()}/"
    bud = GithubApiBudget(Path(home), log=lambda _s: None)

    def _pred(url: str) -> bool:
        u = (url or "").lower()
        if needle not in u:
            return False
        return ("/issues" in u) or ("/pulls" in u)

    return bud.clear_etags_matching(_pred)
