#!/usr/bin/env python3
"""FR #6063 / #6064 / #6069 / #6391: newly closed tickets on watched/focused repos.

Phase-1 events: issue closed, PR merged, PR closed (unmerged).
Phase-2: optional waiting_on registry narrows reports.
Event source (FR #6391): poll GitHub closed issues/PRs for focus repos when
``JEEVES_TICKET_CLOSURE_FIXTURE`` is unset. Fixture stays for tests only.
Wake transport (FR #6391): HTTPS POST to ``JEEVES_TICKET_CLOSURE_WAKE_URL``
(secret from env, never logged). Failed POST stays ``pending`` with backoff.
Legacy GrokBotApi send remains only when wake is forced without a URL (tests).
Never writes queue.json and never assigns work.
FR #6405: GitHub webhook closes are event-first; poll is a slow backup.
Warn (rate-limited) when the poller has no token; never log the token.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    ops_home,
    resolve_focus_path,
    resolve_homes,
    run_check,
)
from wake_brief import WakeBriefError, build_wake_brief
from wake_grok_bot_bob import wake_bob

STATE_NAME = "monitor-ticket-closure.json"
_LEGACY_STATE_NAME = "ticket_closure_state.json"
WAITING_NAME = "ticket-closure-waiting.json"
WAKE_SKIP_NAME = "ticket-closure-wake-skips.json"
# Tests inject a send callable; production prefers HTTPS wake webhook.
_WAKE_SEND = None
# Injectables for FR #6391 tests / chair wiring.
_GITHUB_FETCH: Callable[..., Any] | None = None
_GITHUB_TOKEN: Callable[[], tuple[str, str]] | None = None
_WAKE_HTTP_POST: Callable[..., Any] | None = None
_CLOCK: Callable[[], float] = time.time
WAKE_BACKOFF_S = 60.0
WAKE_BACKOFF_MAX_S = 900.0
NO_TOKEN_WARN_S = 900.0
_LAST_NO_TOKEN_WARN_AT = 0.0
_LOG = None  # optional callable(str) for chair / tests


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _focus_repos(focus_path: Path) -> set[str]:
    data = _load_json(focus_path)
    if not isinstance(data, dict):
        return set()
    repos = data.get("repos")
    if isinstance(repos, dict):
        return {str(k).strip() for k in repos if str(k).strip()}
    if isinstance(repos, list):
        return {str(r).strip() for r in repos if str(r).strip()}
    return set()


def _resolve_repo(repo: str, repos: set[str]) -> str:
    """Map a unique focused short name to owner/repo; leave others unchanged."""
    if "/" in repo:
        return repo
    matches = sorted(r for r in repos if r.rsplit("/", 1)[-1] == repo)
    return matches[0] if len(matches) == 1 else repo


def _event_key(row: dict[str, Any]) -> str:
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("number") or "").strip()
    ev = str(row.get("event") or "").strip().lower()
    ident = str(row.get("delivery_id") or row.get("closed_at") or "").strip()
    return f"{repo}#{num}:{ev}:{ident}"


def _ticket_identity(row: dict[str, Any]) -> str:
    """Stable close identity across webhook delivery_id and poll closed_at (FR #6405)."""
    repo = str(row.get("repo") or "").strip().lower()
    num = str(row.get("number") or "").strip()
    ev = str(row.get("event") or "").strip().lower()
    return f"{repo}#{num}:{ev}"


def _already_handled(seen: dict[str, Any], pending: dict[str, Any], row: dict[str, Any]) -> bool:
    key = _event_key(row)
    if key in seen or key in pending:
        return True
    ident = _ticket_identity(row)
    if not ident.endswith(":") and ident.count("#") == 1:
        for bag in (seen, pending):
            for existing in bag.values():
                if isinstance(existing, dict) and _ticket_identity(existing) == ident:
                    return True
            for k in bag:
                kl = str(k).lower()
                if kl == ident or kl.startswith(ident + ":"):
                    return True
    return False


def _normalize(row: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(row.get("kind") or "").strip().lower()
    ev = str(row.get("event") or "").strip().lower()
    repo = str(row.get("repo") or "").strip()
    try:
        number = int(row.get("number"))
    except (TypeError, ValueError):
        return None
    if kind not in {"issue", "pr"} or not repo or number <= 0:
        return None
    if kind == "issue" and ev != "closed":
        return None
    if kind == "pr" and ev not in {"merged", "closed"}:
        return None
    if kind == "pr" and ev == "closed" and row.get("merged") is True:
        ev = "merged"
    out = {
        "kind": kind,
        "event": ev,
        "repo": repo,
        "number": number,
    }
    closed_at = str(row.get("closed_at") or "").strip()
    delivery = str(row.get("delivery_id") or row.get("deliveryId") or "").strip()
    if closed_at:
        out["closed_at"] = closed_at
    if delivery:
        out["delivery_id"] = delivery
    if kind == "pr":
        out["merged"] = ev == "merged"
    return out


def _filter_repo_events(rows: list[dict[str, Any]], repos: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        norm = _normalize(row)
        if not norm:
            continue
        if repos and norm["repo"] not in repos and norm["repo"].rsplit("/", 1)[-1] not in {
            r.rsplit("/", 1)[-1] for r in repos
        }:
            continue
        norm["repo"] = _resolve_repo(norm["repo"], repos)
        out.append(norm)
    return out


def _load_fixture_events(fixture: Path, repos: set[str]) -> list[dict[str, Any]]:
    data = _load_json(fixture)
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        raw = data.get("closed")
        if isinstance(raw, list):
            rows = [r for r in raw if isinstance(r, dict)]
    elif isinstance(data, list):
        rows = [r for r in data if isinstance(r, dict)]
    return _filter_repo_events(rows, repos)


def _default_github_token() -> tuple[str, str]:
    try:
        import chair_health as ch

        return ch.default_token()
    except Exception:  # noqa: BLE001
        tok = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
        return (tok, "env") if tok else ("", "none")


def _log(msg: str) -> None:
    text = str(msg or "").strip()
    if not text:
        return
    sink = _LOG
    if callable(sink):
        try:
            sink(text)
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        print(text, flush=True)
    except Exception:  # noqa: BLE001
        pass


def _default_github_fetch(url: str, *, token: str = "") -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "bobiverse-jeeves-ticket-closure",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            reset = ""
            try:
                reset = str(e.headers.get("X-RateLimit-Reset") or e.headers.get("x-ratelimit-reset") or "")
            except Exception:  # noqa: BLE001
                reset = ""
            _log(f"WARN ticket-closure GitHub HTTP {e.code} reset={reset or '-'}")
            raise
        return []
    except (OSError, json.JSONDecodeError, urllib.error.URLError):
        return []


def _gh_issue_to_event(repo: str, item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        number = int(item.get("number"))
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    pr = item.get("pull_request")
    closed_at = str(item.get("closed_at") or "").strip()
    title = str(item.get("title") or "").strip()
    if isinstance(pr, dict):
        merged_at = str(item.get("merged_at") or pr.get("merged_at") or "").strip()
        ev = "merged" if merged_at else "closed"
        row: dict[str, Any] = {
            "kind": "pr",
            "event": ev,
            "repo": repo,
            "number": number,
            "merged": ev == "merged",
        }
    else:
        row = {
            "kind": "issue",
            "event": "closed",
            "repo": repo,
            "number": number,
        }
    if closed_at:
        row["closed_at"] = closed_at
    if title:
        row["title"] = title
    return row


def _poll_github_closes(
    repos: set[str],
    *,
    token: str,
    since: str | None,
    fetch: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Poll GitHub Issues API (includes PRs) for closes since *since* (ISO8601).

    When *since* is missing, return no rows (caller seeds the cursor to now so
    the first live poll does not replay historical closes / flood wake).
    """
    fetcher = fetch or _GITHUB_FETCH or _default_github_fetch
    out: list[dict[str, Any]] = []
    if not repos or not token or not since:
        return out
    for repo in sorted(repos):
        if "/" not in repo:
            continue
        q = f"state=closed&sort=updated&direction=asc&per_page=50&since={since}"
        url = f"https://api.github.com/repos/{repo}/issues?{q}"
        try:
            data = fetcher(url, token=token)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            if str(item.get("state") or "").lower() != "closed":
                continue
            ev = _gh_issue_to_event(repo, item)
            if ev:
                out.append(ev)
    return out


def _load_events(
    fixture: Path | None,
    repos: set[str],
    *,
    token: str = "",
    since: str | None = None,
) -> list[dict[str, Any]]:
    if fixture is not None and fixture.is_file():
        return _load_fixture_events(fixture, repos)
    # FR #6391: real source when fixture unset.
    return _poll_github_closes(repos, token=token, since=since)


def _canon_ticket(text: str) -> str:
    return str(text or "").strip().lower().lstrip("#")


def _event_ticket_id(row: dict[str, Any]) -> str:
    return _canon_ticket(f"{row.get('repo')}#{row.get('number')}")


def _load_waiting(chair: Path, digest: Path) -> set[str]:
    """Phase-2 registry. Empty / missing → Phase-1 (all focused closes)."""
    env = (os.environ.get("JEEVES_TICKET_CLOSURE_WAITING") or "").strip()
    paths = []
    if env:
        paths.append(Path(env))
    ops = ops_home(chair, digest)
    paths.extend(
        [
            ops / WAITING_NAME,
            digest / WAITING_NAME,
            chair / WAITING_NAME,
        ]
    )
    for path in paths:
        data = _load_json(path)
        raw = None
        if isinstance(data, dict):
            raw = data.get("waiting_on")
            if raw is None:
                raw = data.get("waitingOn")
        elif isinstance(data, list):
            raw = data
        if not isinstance(raw, list) or not raw:
            continue
        ids = {_canon_ticket(x) for x in raw if str(x).strip()}
        if ids:
            return ids
    return set()


def _wake_url() -> str:
    raw = (
        os.environ.get("JEEVES_TICKET_CLOSURE_WAKE_URL")
        or os.environ.get("JEEVES_BOB_WAKE_URL")
        or ""
    ).strip()
    if not raw:
        return ""
    scheme = (urllib.parse.urlparse(raw).scheme or "").lower()
    # FR #6391 MRB: Bearer/X-Bob-Wake-Secret must not leave the host on cleartext.
    if scheme != "https":
        return ""
    return raw


def _wake_secret() -> str:
    return (
        os.environ.get("JEEVES_TICKET_CLOSURE_WAKE_SECRET")
        or os.environ.get("JEEVES_BOB_WAKE_SECRET")
        or ""
    ).strip()


def _wake_enabled() -> bool:
    if _wake_url():
        return True
    return str(os.environ.get("JEEVES_TICKET_CLOSURE_WAKE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _wake_transport_name() -> str:
    if _wake_url():
        return "webhook"
    if _wake_enabled():
        return "grokbot"
    return "none"


def _default_wake_http_post(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "bobiverse-jeeves-ticket-closure",
            **headers,
        },
        method="POST",
    )
    # Do not follow redirects: Authorization must not hop to another host.
    opener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
    with opener.open(req, timeout=30) as resp:
        status = int(getattr(resp, "status", 200) or 200)
        if status >= 400:
            raise ConnectionError(f"wake HTTP {status}")
        return {"ok": True, "status": status}


def _wake_via_webhook(item: dict[str, Any]) -> dict[str, Any]:
    url = _wake_url()
    if not url:
        return {"ok": False, "woke": False, "error": "no_wake_url", "brief": ""}
    try:
        text = build_wake_brief(item)
    except WakeBriefError:
        return {
            "ok": False,
            "woke": False,
            "error": "invalid_ticket",
            "detail": "need owner/repo and issue/PR number",
            "brief": "",
        }
    headers: dict[str, str] = {}
    secret = _wake_secret()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
        headers["X-Bob-Wake-Secret"] = secret
    payload = {
        "text": text,
        "brief": text,
        "repo": item.get("repo"),
        "number": item.get("number"),
        "kind": item.get("kind"),
        "state": item.get("event") or item.get("state"),
        "title": item.get("title") or "",
        "agent": "Bob",
    }
    poster = _WAKE_HTTP_POST or _default_wake_http_post
    try:
        poster(url, payload, headers)
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "woke": False,
            "error": "wake_unreachable",
            "detail": str(type(e).__name__)[:80],
            "brief": text,
        }
    return {"ok": True, "woke": True, "brief": text, "agent": "Bob", "transport": "webhook"}


def _deliver_wake(item: dict[str, Any]) -> dict[str, Any]:
    if _wake_url():
        return _wake_via_webhook(item)
    return wake_bob(item, send=_WAKE_SEND)


def _load_map(state: Any, key: str) -> dict[str, Any]:
    if isinstance(state, dict) and isinstance(state.get(key), dict):
        return {str(k): v for k, v in state[key].items()}
    return {}


def _write_skip(ops: Path, key: str, ev: dict[str, Any], reason: str) -> bool:
    """Persist an operator-visible skip. False if the file was not written (FR #6081)."""
    path = ops / WAKE_SKIP_NAME
    data = _load_json(path)
    blob = data if isinstance(data, dict) else {}
    blob[key] = {
        "reason": str(reason or "wake_failed")[:80],
        "repo": ev.get("repo"),
        "number": ev.get("number"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(blob, separators=(",", ":"), sort_keys=True), encoding="utf-8")
        return True
    except OSError:
        return False



def _maybe_warn_no_token(*, now: float, token_source: str) -> bool:
    """Rate-limited WARN when poller has no GitHub token. Never logs the token."""
    global _LAST_NO_TOKEN_WARN_AT
    src = (token_source or "").strip().lower() or "none"
    if src != "none":
        return False
    if _LAST_NO_TOKEN_WARN_AT and (now - float(_LAST_NO_TOKEN_WARN_AT)) < NO_TOKEN_WARN_S:
        return False
    _LAST_NO_TOKEN_WARN_AT = now
    _log(
        "WARN ticket-closure: no GitHub token "
        "(gh_filer config/github.token or GITHUB_TOKEN/GH_TOKEN); "
        "poll backup skipped until a token is available"
    )
    return True


def close_event_from_github_webhook(
    event: str,
    payload: dict[str, Any],
    *,
    delivery_id: str = "",
) -> dict[str, Any] | None:
    """Map issues/pull_request closed|merged webhook payloads to a close event."""
    if not isinstance(payload, dict):
        return None
    ev = str(event or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()
    repo_obj = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    repo = str(repo_obj.get("full_name") or "").strip()
    if not repo and isinstance(payload.get("repo"), str):
        repo = str(payload.get("repo") or "").strip()
    did = str(delivery_id or payload.get("delivery_id") or "").strip()
    if ev == "issues" and action == "closed":
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else None
        if not issue:
            return None
        try:
            number = int(issue.get("number"))
        except (TypeError, ValueError):
            return None
        row: dict[str, Any] = {
            "kind": "issue",
            "event": "closed",
            "repo": repo,
            "number": number,
            "source": "webhook",
        }
        ca = str(issue.get("closed_at") or "").strip()
        if ca:
            row["closed_at"] = ca
        title = str(issue.get("title") or "").strip()
        if title:
            row["title"] = title
        if did:
            row["delivery_id"] = did
        return row
    if ev == "pull_request" and action == "closed":
        pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else None
        if not pr:
            return None
        try:
            number = int(pr.get("number"))
        except (TypeError, ValueError):
            return None
        merged_at = str(pr.get("merged_at") or "").strip()
        merged = bool(pr.get("merged")) or bool(merged_at)
        row = {
            "kind": "pr",
            "event": "merged" if merged else "closed",
            "repo": repo,
            "number": number,
            "merged": merged,
            "source": "webhook",
        }
        ca = str(pr.get("closed_at") or merged_at or "").strip()
        if ca:
            row["closed_at"] = ca
        if merged_at:
            row["merged_at"] = merged_at
        title = str(pr.get("title") or "").strip()
        if title:
            row["title"] = title
        if did:
            row["delivery_id"] = did
        return row
    return None


def _persist_state(
    state_path: Path,
    *,
    seen: dict[str, Any],
    pending: dict[str, Any],
    poll_cursor: str | None,
    last_poll_at: Any,
    last_wake_at: Any,
    extra: dict[str, Any] | None = None,
) -> None:
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        blob: dict[str, Any] = {
            "seen": seen,
            "pending": pending,
            "pending_count": len(pending),
            "wake_transport": _wake_transport_name(),
        }
        if last_poll_at is not None:
            blob["last_poll_at"] = last_poll_at
        if last_wake_at is not None:
            blob["last_wake_at"] = last_wake_at
        if poll_cursor:
            blob["poll_cursor"] = poll_cursor
        if extra:
            blob.update(extra)
        tmp = state_path.with_name(f"{state_path.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps(blob, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp, state_path)
    except OSError:
        pass


def _drain_pending_wakes(
    ops: Path,
    *,
    seen: dict[str, Any],
    pending: dict[str, Any],
    now: float,
    last_wake_at: Any,
) -> tuple[int, int, Any]:
    woke_n = 0
    skip_n = 0
    if not _wake_enabled():
        return woke_n, skip_n, last_wake_at
    for key, ev in list(pending.items()):
        item = ev if isinstance(ev, dict) else {}
        try:
            nxt = float(item.get("next_retry_at") or 0.0)
        except (TypeError, ValueError):
            nxt = 0.0
        if nxt > now:
            continue
        result = _deliver_wake(item)
        if result.get("woke"):
            clean = {k: v for k, v in item.items() if k not in {"next_retry_at", "fail_count"}}
            seen[key] = clean
            pending.pop(key, None)
            woke_n += 1
            last_wake_at = now
            continue
        reason = str(result.get("error") or "wake_failed")
        if reason in {"wake_unreachable", "bob_unreachable", "no_wake_url"}:
            fails = int(item.get("fail_count") or 0) + 1
            backoff = min(WAKE_BACKOFF_MAX_S, WAKE_BACKOFF_S * (2 ** max(0, fails - 1)))
            item = dict(item)
            item["fail_count"] = fails
            item["next_retry_at"] = now + backoff
            item["last_error"] = reason
            pending[key] = item
            continue
        if not _write_skip(ops, key, item, reason):
            continue
        seen[key] = item
        pending.pop(key, None)
        skip_n += 1
    return woke_n, skip_n, last_wake_at


def ingest_github_webhook(
    home: Path | str,
    event: str,
    payload: dict[str, Any],
    *,
    delivery_id: str = "",
    chair_home: Path | str | None = None,
    digest_home: Path | str | None = None,
) -> dict[str, Any]:
    """FR #6405: apply one GitHub close webhook through the same pending/seen/wake path."""
    row = close_event_from_github_webhook(event, payload, delivery_id=delivery_id)
    if not row:
        return {"ok": True, "accepted": False, "reason": "not_a_close"}
    digest = Path(digest_home or home)
    chair = Path(chair_home or home)
    focus_path = resolve_focus_path(chair, digest)
    repos = _focus_repos(focus_path)
    repo = str(row.get("repo") or "").strip()
    if repo and repos and repo not in repos:
        return {"ok": True, "accepted": False, "reason": "not_focused"}
    waiting = _load_waiting(chair, digest)
    if waiting and _event_ticket_id(row) not in waiting:
        return {"ok": True, "accepted": False, "reason": "not_waiting"}
    ops = ops_home(chair, digest)
    state_path = ops / STATE_NAME
    state = _load_json(state_path)
    if not isinstance(state, dict):
        state = {}
    seen = _load_map(state, "seen")
    pending = _load_map(state, "pending")
    poll_cursor = str(state.get("poll_cursor") or "").strip() or None
    last_wake_at = state.get("last_wake_at")
    now = float(_CLOCK())
    key = _event_key(row)
    if _already_handled(seen, pending, row):
        return {"ok": True, "accepted": False, "reason": "duplicate", "key": key}
    try:
        row = dict(row)
        row["brief"] = build_wake_brief(row)
    except WakeBriefError as exc:
        return {"ok": False, "accepted": False, "reason": "brief", "error": type(exc).__name__}
    pending[key] = row
    woke_n, skip_n, last_wake_at = _drain_pending_wakes(
        ops, seen=seen, pending=pending, now=now, last_wake_at=last_wake_at
    )
    _persist_state(
        state_path,
        seen=seen,
        pending=pending,
        poll_cursor=poll_cursor,
        last_poll_at=state.get("last_poll_at"),
        last_wake_at=last_wake_at,
        extra={"last_webhook_at": now, "token_source": str(state.get("token_source") or "")},
    )
    return {
        "ok": True,
        "accepted": True,
        "key": key,
        "woke": woke_n,
        "wake_skips": skip_n,
        "pending_count": len(pending),
    }


def check(args):
    chair, digest = resolve_homes(args)
    focus_path = resolve_focus_path(chair, digest)
    repos = _focus_repos(focus_path)
    fx = (os.environ.get("JEEVES_TICKET_CLOSURE_FIXTURE") or "").strip()
    fixture = Path(fx) if fx else None
    ops = ops_home(chair, digest)
    state_path = ops / STATE_NAME
    state = _load_json(state_path)
    if state is None:
        state = _load_json(ops / _LEGACY_STATE_NAME) or _load_json(
            chair / _LEGACY_STATE_NAME
        )
    if not isinstance(state, dict):
        state = {}
    seen = _load_map(state, "seen")
    pending = _load_map(state, "pending")
    poll_cursor = str(state.get("poll_cursor") or "").strip() or None
    token_loader = _GITHUB_TOKEN or _default_github_token
    token, _tok_src = token_loader()
    token_source = str(_tok_src or ("env" if token else "none")).strip() or "none"
    if not token:
        token_source = "none"
    now = float(_CLOCK())
    warned = False
    # First live poll: seed cursor to now; do not replay historical closes.
    if fixture is None and poll_cursor is None:
        poll_cursor = _utc_iso_now()
        events: list[dict[str, Any]] = []
    elif fixture is None and not token:
        events = []
        warned = _maybe_warn_no_token(now=now, token_source=token_source)
    else:
        events = _load_events(fixture, repos, token=token or "", since=poll_cursor)
    waiting = _load_waiting(chair, digest)
    # Advance cursor from every fetched close before the waiting filter so a
    # Phase-2 registry cannot stall the global cursor on non-waiting pages.
    newest_closed = poll_cursor
    for ev in events:
        ca = str(ev.get("closed_at") or "").strip()
        if ca and (newest_closed is None or ca > newest_closed):
            newest_closed = ca
    if waiting:
        events = [ev for ev in events if _event_ticket_id(ev) in waiting]
    closed = []
    for ev in events:
        if _already_handled(seen, pending, ev):
            continue
        key = _event_key(ev)
        row = dict(ev)
        try:
            row["brief"] = build_wake_brief(row)
        except WakeBriefError:
            continue
        row.setdefault("source", "poll")
        closed.append(row)
        pending[key] = row
    last_wake_at = state.get("last_wake_at")
    woke_n, skip_n, last_wake_at = _drain_pending_wakes(
        ops, seen=seen, pending=pending, now=now, last_wake_at=last_wake_at
    )
    last_poll_at = now
    if newest_closed:
        poll_cursor = newest_closed
    _persist_state(
        state_path,
        seen=seen,
        pending=pending,
        poll_cursor=poll_cursor,
        last_poll_at=last_poll_at,
        last_wake_at=last_wake_at,
        extra={
            "token_source": token_source,
            "ticket_closure_token_source": token_source,
        },
    )
    ok = not closed
    findings = []
    remediation = []
    if closed:
        findings.append(f"{len(closed)} newly closed ticket(s) on watched/focused repos")
        remediation.append("report via intake only; do not enqueue or assign")
    return (
        {
            "ok": ok,
            "closed": closed,
            "closed_count": len(closed),
            "repos": sorted(repos),
            "waiting_on": sorted(waiting),
            "woke": woke_n,
            "wake_skips": skip_n,
            "pending_count": len(pending),
            "last_poll_at": last_poll_at,
            "last_wake_at": last_wake_at,
            "wake_transport": _wake_transport_name(),
            "token_source": token_source,
            "ticket_closure_token_source": token_source,
            "no_token_warned": warned,
            "findings": findings,
            "remediation": remediation,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "ticket_closure",
        "FR #6063: newly closed issues/PRs on focused repos (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
