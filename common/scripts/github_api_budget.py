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
# Stop non-essential REST when GitHub remaining drops below this floor.
BACKOFF_FLOOR = 500
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
        else:
            self.used = int(doc.get("used") or 0)
            self.hour = stored_hour
            self.rate_remaining = (
                int(doc["rate_remaining"]) if doc.get("rate_remaining") is not None else None
            )
            self.rate_reset = (
                float(doc["rate_reset"]) if doc.get("rate_reset") is not None else None
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

    def in_backoff(self) -> bool:
        self._roll_hour()
        if self.remaining_budget() <= 0:
            return True
        if self.rate_remaining is not None and self.rate_remaining < self.floor:
            return True
        return False

    def allow(self, path: str, *, essential: bool = False) -> bool:
        """Whether a REST call may proceed. Startup reconcile may use ``essential=True``."""
        self._roll_hour()
        if essential:
            return self.remaining_budget() > 0 or self.used == 0
        if self.in_backoff():
            self._log_backoff_once(path)
            return False
        return True

    def _log_backoff_once(self, path: str) -> None:
        if self._backoff_logged:
            return
        self._backoff_logged = True
        rem = self.rate_remaining if self.rate_remaining is not None else "?"
        self.log(
            f"WARN github-api backoff path={path} used={self.used}/{self.budget_per_hour} "
            f"remaining={rem} reset={_fmt_reset_local(self.rate_reset, now=self.clock())}"
        )

    def note_headers(self, hdrs) -> None:
        if hdrs is None:
            return
        try:
            get = getattr(hdrs, "get", None)
            if not callable(get):
                return
            rem = get("X-RateLimit-Remaining") or get("x-ratelimit-remaining")
            reset = get("X-RateLimit-Reset") or get("x-ratelimit-reset")
            if rem is not None and str(rem).strip() != "":
                self.rate_remaining = int(rem)
            if reset is not None and str(reset).strip() != "":
                self.rate_reset = float(reset)
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
        timeout: float = 30.0,
        opener: Callable[..., Any] | None = None,
    ) -> Any:
        """GET with If-None-Match. Returns JSON body, or ``NOT_MODIFIED`` on 304.

        304 does not charge the hourly budget. Other successes charge one call.
        """
        if not self.allow(path, essential=essential):
            raise RuntimeError(f"github-api backoff path={path}")

        hdrs = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-jeeves",
        }
        if token:
            hdrs["Authorization"] = "Bearer " + token
        etag = self.get_etag(url)
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
    opener: Callable[..., Any] | None = None,
) -> Callable[[str], Any]:
    """``fetch_json(url)`` seam for resync: raises ``NotModified`` on 304."""

    def fetch(url: str):
        out = budget.conditional_get(
            url, token=token, path=path, essential=essential, opener=opener
        )
        if out is NOT_MODIFIED:
            raise NotModified(url)
        return out

    return fetch
