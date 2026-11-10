#!/usr/bin/env python3
"""FR #6063 / #6064 / #6069 / #6391: newly closed tickets on watched/focused repos.

Phase-1 events: issue closed, PR merged, PR closed (unmerged).
Phase-2: optional waiting_on registry narrows reports.
Event source (FR #6391 / #6400): poll GitHub closed issues/PRs for focus repos when
``JEEVES_TICKET_CLOSURE_FIXTURE`` is unset. Per-repo ``poll_cursors`` + page
pagination (FR #6400). Fixture stays for tests only.
Wake transport (FR #6391): HTTPS POST to ``JEEVES_TICKET_CLOSURE_WAKE_URL``
(secret from env, never logged). Failed POST stays ``pending`` with backoff.
Legacy GrokBotApi send remains only when wake is forced without a URL (tests).
Never writes queue.json and never assigns work.
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
POLL_PER_PAGE = 50
POLL_MAX_PAGES = 20


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
            body = json.loads(resp.read().decode("utf-8"))
            link = resp.headers.get("Link") if hasattr(resp, "headers") else None
            if link:
                return body, link
            return body
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
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


def _parse_link_next(link_header: str | None) -> str | None:
    """Return the URL for rel=next from a GitHub Link header, if present."""
    if not link_header:
        return None
    for part in str(link_header).split(","):
        chunk = part.strip()
        if 'rel="next"' not in chunk and "rel=next" not in chunk:
            continue
        if "<" in chunk and ">" in chunk:
            return chunk[chunk.index("<") + 1 : chunk.index(">")].strip()
    return None


def _fetch_page(
    fetcher: Callable[..., Any],
    url: str,
    *,
    token: str,
) -> tuple[list[Any], str | None]:
    """Call *fetcher*; accept a bare list or ``(list, link_header)`` tuple."""
    raw = fetcher(url, token=token)
    if isinstance(raw, tuple) and len(raw) >= 1:
        data = raw[0]
        link = raw[1] if len(raw) > 1 else None
        return (data if isinstance(data, list) else [], link if isinstance(link, str) else None)
    if isinstance(raw, list):
        return raw, None
    return [], None


def _poll_github_closes(
    repos: set[str],
    *,
    token: str,
    cursors: dict[str, str],
    fetch: Callable[..., Any] | None = None,
    per_page: int = POLL_PER_PAGE,
    max_pages: int = POLL_MAX_PAGES,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Poll GitHub Issues API per repo with pagination (FR #6400).

    Each focused repo keeps its own ``since`` cursor. Pages continue via
    ``page=`` until a short page, or via ``Link: rel=next`` when the fetcher
    returns a link header. Cursors advance from every fetched close before any
    waiting filter is applied by the caller.
    """
    fetcher = fetch or _GITHUB_FETCH or _default_github_fetch
    out: list[dict[str, Any]] = []
    updated = {str(k): str(v) for k, v in cursors.items() if str(k).strip() and str(v).strip()}
    if not repos or not token:
        return out, updated
    for repo in sorted(repos):
        if "/" not in repo:
            continue
        since = str(updated.get(repo) or "").strip()
        if not since:
            continue
        page = 1
        next_url: str | None = None
        repo_newest = since
        while page <= max_pages:
            if next_url:
                url = next_url
            else:
                q = (
                    f"state=closed&sort=updated&direction=asc"
                    f"&per_page={int(per_page)}&page={page}&since={since}"
                )
                url = f"https://api.github.com/repos/{repo}/issues?{q}"
            try:
                data, link = _fetch_page(fetcher, url, token=token)
            except Exception:  # noqa: BLE001
                break
            for item in data:
                if not isinstance(item, dict):
                    continue
                if str(item.get("state") or "").lower() != "closed":
                    continue
                ev = _gh_issue_to_event(repo, item)
                if not ev:
                    continue
                out.append(ev)
                ca = str(ev.get("closed_at") or "").strip()
                if ca and ca > repo_newest:
                    repo_newest = ca
            next_url = _parse_link_next(link)
            if next_url:
                page += 1
                continue
            if len(data) < int(per_page):
                break
            page += 1
        updated[repo] = repo_newest
    return out, updated


def _load_events(
    fixture: Path | None,
    repos: set[str],
    *,
    token: str = "",
    cursors: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if fixture is not None and fixture.is_file():
        return _load_fixture_events(fixture, repos), dict(cursors or {})
    # FR #6391 / #6400: real source when fixture unset.
    return _poll_github_closes(repos, token=token, cursors=dict(cursors or {}))


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
    raw_cursors = state.get("poll_cursors")
    poll_cursors: dict[str, str] = {}
    if isinstance(raw_cursors, dict):
        for k, v in raw_cursors.items():
            ks, vs = str(k).strip(), str(v).strip()
            if ks and vs:
                poll_cursors[ks] = vs
    token_loader = _GITHUB_TOKEN or _default_github_token
    token, _tok_src = token_loader()
    now = float(_CLOCK())
    focused = {r for r in repos if "/" in r}
    # First live poll: seed per-repo cursors to now; do not replay history.
    if fixture is None and not poll_cursors and not poll_cursor:
        seed = _utc_iso_now()
        poll_cursors = {r: seed for r in focused}
        poll_cursor = seed
        events: list[dict[str, Any]] = []
    elif fixture is None:
        # Migrate legacy global cursor into any missing per-repo slots.
        fallback = poll_cursor or _utc_iso_now()
        for r in focused:
            if r not in poll_cursors:
                poll_cursors[r] = fallback
        events, poll_cursors = _load_events(
            fixture, repos, token=token or "", cursors=poll_cursors
        )
    else:
        events, poll_cursors = _load_events(
            fixture, repos, token=token or "", cursors=poll_cursors
        )
    waiting = _load_waiting(chair, digest)
    # Cursors already advanced inside _poll_github_closes from all pages.
    newest_closed = poll_cursor
    for ca in poll_cursors.values():
        if ca and (newest_closed is None or ca > newest_closed):
            newest_closed = ca
    if waiting:
        events = [ev for ev in events if _event_ticket_id(ev) in waiting]
    closed = []
    handled = set(seen) | set(pending)
    for ev in events:
        key = _event_key(ev)
        if key in handled:
            continue
        row = dict(ev)
        try:
            row["brief"] = build_wake_brief(row)
        except WakeBriefError:
            continue
        closed.append(row)
        pending[key] = row
        handled.add(key)
    woke_n = 0
    skip_n = 0
    last_wake_at = state.get("last_wake_at")
    if _wake_enabled():
        for key, ev in list(pending.items()):
            item = ev if isinstance(ev, dict) else {}
            # FR #6391: honour retry backoff on failed webhook POSTs.
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
            # FR #6391: transport failures stay pending (retry). Invalid tickets can skip.
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
    last_poll_at = now
    if newest_closed:
        poll_cursor = newest_closed
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "seen": seen,
            "pending": pending,
            "last_poll_at": last_poll_at,
            "pending_count": len(pending),
            "wake_transport": _wake_transport_name(),
        }
        if last_wake_at is not None:
            blob["last_wake_at"] = last_wake_at
        if poll_cursor:
            blob["poll_cursor"] = poll_cursor
        if poll_cursors:
            blob["poll_cursors"] = dict(sorted(poll_cursors.items()))
        tmp = state_path.with_name(f"{state_path.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps(blob, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp, state_path)
    except OSError:
        pass
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
