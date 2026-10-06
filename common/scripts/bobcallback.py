#!/usr/bin/env python3
"""Digest callback: report/git/intake/jira; public GET digest (#174, #149).

Public IIS front-door GET is **/bob/v1/report** only (FR #149 / FR #354). Local bobcallback
also serves `/bob/v1/digest` and `/digest` with the same JSON body; those aliases are not
published through the irc.ntsa.uk IIS rewrite today (GET https://irc.ntsa.uk/bob/v1/digest -> 404).

Durable POST envelopes go through webhook_queue; chair announces on #bobiverse.

NO PASSWORD / SHARED SECRET anywhere (v0.1.16, Simon): no route checks ``X-Bob-Secret`` (a stray
header is ignored and never stored). Abuse protection instead of a secret, all enforced here:
body size caps (413), strict JSON-object + op/event schema validation, per-machine rate limiting
(429), GitHub hooks only for allow-listed owners/events, and POSTs on /bob/v1/report only from
machine ids on the roster that **Jeeves publishes** in ``registered-machines.json``. The receiver
only READS that file (``bobreport.roster_machine_ids``); it never talks to ChanServ or IRC - the
chair is the only ChanServ client.
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import bobreport
import intake
import jira_webhook
import webhook_queue

REPORT_PATH = "/bob/v1/report"
GIT_WEBHOOK_PATH = "/bob/v1/git"
INTAKE_PATH = "/bob/v1/intake"
JIRA_PATH = "/bob/v1/jira"
DIGEST_PATH = "/bob/v1/digest"
HEALTH_PATH = "/health"
HEALTH_PROBE_ZEN = "jeeves-health-probe"
DIGEST_ALIAS = "/digest"
HEALTH_WATCHDOG_ENV = "BOB_CALLBACK_HEALTH_S"
DEFAULT_HEALTH_WATCHDOG_S = 30.0
# Public readers (IIS / browsers / UAT): use reportUrl. Local bobcallback still answers DIGEST_*.
PUBLIC_DIGEST_PATH = REPORT_PATH
CLI_DESCRIPTION = (
    "POST /bob/v1/report|/bob/v1/git|/bob/v1/intake|/bob/v1/jira; "
    "front-door GET is /bob/v1/report (local bobcallback also serves /bob/v1/digest); "
    "GET /bob/v1/jira"
)
ALLOW_ENV = "BOB_REPORT_ALLOW"
DEFAULT_PORT = 7700
# Public read paths (GET/HEAD). REPORT_PATH is also the write URL (POST).
DIGEST_GET_PATHS = frozenset({DIGEST_PATH, DIGEST_ALIAS, REPORT_PATH})
POST_ROUTES = frozenset({REPORT_PATH, GIT_WEBHOOK_PATH, INTAKE_PATH, JIRA_PATH})
# v0.1.16: NO route needs a password/secret. Every POST route is open and protected by input
# validation, size limits, per-machine rate limiting and the Jeeves-published roster instead.
MAX_BODY_BYTES = 1024 * 1024          # hard cap for any POST body (413 above)
MAX_REPORT_BYTES = 256 * 1024         # /bob/v1/report bodies are tiny status docs
REPORT_RATE_ENV = "BOB_REPORT_RATE_PER_MIN"
DEFAULT_REPORT_RATE_PER_MIN = 120     # per machine id (tray posts ~2/min, workers a few more)
GIT_OWNERS_ENV = "BOB_GIT_OWNERS"     # comma list of GitHub owners whose hooks we accept
DEFAULT_GIT_OWNERS = ("SimonBarnett",)
GIT_RATE_PER_MIN = 120                # per repository
GIT_EVENTS = frozenset({"ping", "push", "issues", "pull_request"})


def load_allow_ips() -> set[str]:
    raw = (os.environ.get(ALLOW_ENV) or "").strip()
    if raw:
        return {p.strip() for p in raw.split(",") if p.strip()}
    return {"127.0.0.1", "::1"}


def resolve_listen_port(port: int) -> int:
    """Never bind an ephemeral port: 0 → BOB_REPORT_PORT or 7700."""
    p = int(port or 0)
    if p > 0:
        return p
    env = int(os.environ.get("BOB_REPORT_PORT") or "0")
    if env > 0:
        return env
    return DEFAULT_PORT


def _check_post_route(
    verb: str, route: str, peer_ip: str, allow_ips: set[str] | None
) -> tuple[int, set[str]] | tuple[int, bytes]:
    """Return (0, allow_set) on success, or (http_code, body) on failure."""
    allow = allow_ips if allow_ips is not None else load_allow_ips()
    if route not in POST_ROUTES:
        return 404, b""
    if verb != "POST":
        return 405, b""
    ip = (peer_ip or "").split("%", 1)[0]
    if allow and ip not in allow:
        return 403, b""
    return 0, allow


def report_rate_per_min() -> int:
    try:
        return max(1, int(os.environ.get(REPORT_RATE_ENV) or DEFAULT_REPORT_RATE_PER_MIN))
    except ValueError:
        return DEFAULT_REPORT_RATE_PER_MIN


def git_owners() -> set[str]:
    raw = (os.environ.get(GIT_OWNERS_ENV) or "").strip()
    names = [x.strip() for x in raw.split(",") if x.strip()] or list(DEFAULT_GIT_OWNERS)
    return {n.lower() for n in names}


def _announce(home: Path, text: str) -> bool:
    return bobreport.enqueue_chair_fleet_privmsg(home, text)


def handle_digest_get(home: Path, briefer_nick: str = "") -> tuple[int, bytes]:
    """Public readable digest (#174). No secret; nothing in digest is secure."""
    briefer = (briefer_nick or "").strip() or "digest"
    doc = bobreport.build_digest_object(home, briefer)
    body = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    return 200, body


def handle_health_get(home: Path) -> tuple[int, bytes]:
    """FR #1136 / #1388 / #2902: liveness + lock age/holder + last digest write.

    A lock held by *this* live PID past ``lock_stale_s`` is still healthy (a write is
    in progress). Only foreign/dead/absent-stale ages and an unwritable digest dir
    make ``ok`` false (HTTP 503).
    """
    bobreport.break_stale_digest_lock(home)
    age = bobreport.digest_lock_age_s(home)
    holder = bobreport.digest_lock_holder_pid(home)
    last = bobreport.last_digest_write_iso(home)
    stale_limit = bobreport.digest_lock_stale_s()
    foreign_limit = bobreport.digest_lock_foreign_s()
    me = os.getpid()
    own_live = (
        holder is not None
        and int(holder) == int(me)
        and bobreport._pid_alive(int(holder))
    )
    # FR #2902: own live holder never trips lock_ok - age alone is not failure.
    lock_ok = age is None or age < stale_limit or own_live
    writable = True
    try:
        dig = bobreport.digest_path(home)
        dig.parent.mkdir(parents=True, exist_ok=True)
        probe = dig.with_name(f".health-write-probe.{os.getpid()}")
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        writable = False
    ok = bool(lock_ok and writable)
    doc = {
        "ok": ok,
        "lock_age_s": age,
        "lock_stale_s": stale_limit,
        "lock_foreign_s": foreign_limit,
        "lock_pid": holder,
        "pid": me,
        "lock_own": bool(own_live),
        "last_digest_write": last,
        "digest_writable": writable,
    }
    return (200 if ok else 503), json.dumps(doc, separators=(",", ":")).encode("utf-8")

def _parse_json_body(body: bytes | str, *, scan_secret: bool = True) -> dict | None:
    """Parse JSON object. scan_secret=True rejects bodies that look like secrets (report path).

    Git webhooks must use scan_secret=False (FR #206): issue bodies may *mention*
    marker strings without being secrets; only the announce line is checked later.
    """
    if isinstance(body, bytes):
        raw = body.decode("utf-8", "replace")
    else:
        raw = body or ""
    if scan_secret and bobreport.looks_like_secret(raw):
        return None
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _log_git_reject(
    reason: str,
    *,
    event: str = "",
    repo: str = "",
    number: str = "",
    marker: str = "",
) -> None:
    """One-line reject reason; marker *name* only, never a secret value."""
    bits = [f"reason={reason}"]
    if event:
        bits.append(f"event={event}")
    if repo:
        bits.append(f"repo={repo}")
    if number:
        bits.append(f"number={number}")
    if marker:
        bits.append(f"marker={marker}")
    print("INFO git webhook reject " + " ".join(bits), flush=True)


def _safe_headers(headers: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        name = str(k)
        if name.lower() in ("x-bob-secret", "x-bob-intake-key", "authorization"):
            continue
        out[name] = str(v)[:256]
    return out


def _enqueue_post(
    home: Path,
    *,
    kind: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return webhook_queue.enqueue(
        home,
        kind=kind,
        payload=payload,
        headers=_safe_headers(headers),
        meta=meta or {},
    )


def _try_report_handler_failure(
    home: Path,
    filer: intake.GitHubFiler | None,
    *,
    route: str,
    err: str,
) -> None:
    """After auth: best-effort intake issue + announce; never include secrets."""
    import hashlib

    safe_err = intake._redact(str(err or "error")[:400])  # noqa: SLF001 — shared redactor
    _announce(home, f"WEBHOOK fail route={route} err={safe_err[:160]}")
    if filer is None:
        return
    digest = hashlib.sha256(f"{route}|{safe_err}".encode("utf-8")).hexdigest()[:16]
    payload = {
        "kind": "issue",
        "repo": "SimonBarnett/bobiverse",
        "title": f"webhook failure: {route}",
        "body": f"bobcallback handler failure after auth.\n\nroute: `{route}`\nerr: {safe_err}\n",
        "source": {
            "agent": "bobcallback",
            "machine": "",
            "skill_book": "bobiverse",
            "version": "",
        },
        "idempotency_key": f"whfail-{route}-{digest}",
    }
    try:
        intake.process_intake(home, payload, filer=filer, client_ip="127.0.0.1")
    except Exception:
        return


def handle_git_webhook(
    headers: dict[str, str],
    body: bytes | str,
    home: Path,
    *,
    envelope_id: str | None = None,
    rate: intake.RateLimiter | None = None,
) -> tuple[int, bytes]:
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    event = (hdrs.get("x-github-event") or "").strip()
    if not event:
        _log_git_reject("no event")
        return 400, b""
    if len(body or b"") > MAX_BODY_BYTES:
        _log_git_reject("too large", event=event)
        return 413, b""
    if event.lower() not in GIT_EVENTS:
        _log_git_reject("unsupported event", event=event)
        return 400, b""
    # Do not secret-scan the full JSON (FR #206).
    payload = _parse_json_body(body, scan_secret=False)
    if payload is None:
        _log_git_reject("invalid json", event=event)
        return 400, b""
    # No HMAC secret: accept only hooks for allow-listed GitHub owners (BOB_GIT_OWNERS).
    full = bobreport._github_repo_name(payload)  # noqa: SLF001
    owner, _, name = full.partition("/")
    if not owner or not name or owner.lower() not in git_owners():
        _log_git_reject("repo not allowed", event=event, repo=full[:80])
        return 403, b""
    if event.lower() == "ping" and str(payload.get("zen") or "") == HEALTH_PROBE_ZEN:
        # Jeeves' own 30-min webhook health probe (chair_health.py): proves the route + owner gate end to end,
        # but must not enqueue a job or announce on #bobiverse.
        return 204, b""
    if rate is not None and not rate.allow("git:" + full.lower()):
        _log_git_reject("rate limited", event=event, repo=full[:80])
        return 429, b""
    env = _enqueue_post(
        home,
        kind="git",
        payload=payload,
        headers=headers,
        meta={"event": event, "envelope_id": envelope_id or ""},
    )
    eid = str(env.get("id") or "")
    out = bobreport.apply_git_webhook(home, event, payload)
    if not out.ok:
        repo = ""
        number = ""
        if isinstance(payload, dict):
            repo = bobreport._github_repo_name(payload)
            issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else None
            pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else None
            ent = issue or pr
            if isinstance(ent, dict) and ent.get("number") is not None:
                number = str(ent.get("number"))
        _log_git_reject(out.err or "error", event=event, repo=repo, number=number)
        # 400 only for malformed request shape; other failures are server-side.
        if out.err in ("no event", "malformed", "announce"):
            if eid:
                webhook_queue.mark_done(home, eid, result={"ok": False, "err": out.err})
            return 400, b""
        _announce(home, f"GIT fail event={event} err={out.err or 'error'}")
        return 500, b""
    if eid:
        webhook_queue.mark_done(home, eid, result={"ok": True})
    return 204, b""


WORKER_OPS = frozenset({"worker-upsert", "worker-remove", "worker-work"})
REPORT_OPS = frozenset({"merge", "delete-worker", "shop-down"}) | WORKER_OPS
# Underscore / short aliases seen from older tray / ear clients.
_REPORT_OP_ALIASES = {
    "worker_upsert": "worker-upsert",
    "worker_remove": "worker-remove",
    "worker_work": "worker-work",
    "upsert": "worker-upsert",
    "remove": "worker-remove",
    "work": "worker-work",
    "working_on": "merge",
    "presence": "merge",
    "status": "merge",
}


def coerce_report_payload(payload: dict) -> dict:
    """Normalize legacy POST /bob/v1/report bodies into REPORT_OPS shape.

    Fleet boxes historically POST machine + pcent/working_on with no ``op``, or use
    underscore aliases. Rejects still happen for empty/unknown bodies — those log
    ``op=`` + keys so we can find the client.
    """
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    raw = str(out.get("op") or "").strip().lower()
    if raw in _REPORT_OP_ALIASES:
        out["op"] = _REPORT_OP_ALIASES[raw]
        return out
    if raw:
        return out
    # Missing/empty op: infer merge vs worker-work from fields.
    mid = bobreport.normalize_machine_id(str(out.get("machine") or out.get("id") or ""))
    if not mid:
        return out
    nick = str(out.get("nick") or "").strip()
    if nick and bobreport.is_worker_nick(nick):
        # Prefer worker-work when a seat nick is present.
        if out.get("state") in (None, "") and "working_on" in out:
            text = str(out.get("working_on") or "").strip()
            out["state"] = "idle" if not text else "doing"
            if text and out.get("work") in (None, ""):
                out["work"] = text
        out["op"] = "worker-work" if out.get("state") not in (None, "") else "worker-upsert"
        return out
    # Machine presence / pcent / working_on without nick → merge (apply_callback path).
    merge_keys = (
        "pcent",
        "working_on",
        "cursor_pools",
        "period_end",
        "cursor_period_end",
        "online",
        "workers",
        "worker_list",
        "pid",
    )
    if any(k in out for k in merge_keys):
        out["op"] = "merge"
    return out


def validate_report_payload(home: Path, payload: dict) -> tuple[int, str, str]:
    """Schema + roster gate for POST /bob/v1/report. Returns (0, machine_id, "") or (http, "", why).

    - ``op`` must be one of REPORT_OPS (``git-claim`` is NOT a network op: Jeeves claims locally);
    - ``machine``/``id`` must be a syntactically valid machine id;
    - that id must be on the roster Jeeves published (registered-machines.json). Pure file read;
      an empty/missing roster accepts nothing. No ChanServ/IRC call happens here.
    """
    op = str(payload.get("op") or "").strip().lower()
    if op not in REPORT_OPS:
        return 400, "", "bad op"
    mid = bobreport.normalize_machine_id(str(payload.get("machine") or payload.get("id") or ""))
    if not mid:
        return 400, "", "bad machine"
    if not bobreport.is_roster_machine(home, mid):
        return 403, "", "not on roster"
    for key in ("pid",):
        val = payload.get(key)
        if val is not None and val != "" and not str(val).isdigit():
            return 400, "", "bad pid"
    if op in WORKER_OPS:
        if not bobreport.is_worker_nick(str(payload.get("nick") or "")):
            return 400, "", "bad nick"
        st = payload.get("state")
        if st not in (None, "") and str(st).strip().lower() not in bobreport.WORKER_STATES:
            return 400, "", "bad state"
        if op == "worker-work" and st in (None, ""):
            return 400, "", "state required"
        work = payload.get("work")
        if work is not None and (not isinstance(work, str) or len(work) > 400):
            return 400, "", "bad work"
    return 0, mid, ""


def handle_report_post(
    headers: dict[str, str],
    body: bytes | str,
    home: Path,
    briefer_nick: str = "",
    *,
    filer: intake.GitHubFiler | None = None,
    rate: intake.RateLimiter | None = None,
) -> tuple[int, bytes]:
    if len(body or b"") > MAX_REPORT_BYTES:
        return 413, b""
    payload = _parse_json_body(body)
    if payload is None:
        return 400, b""
    if isinstance(payload, dict):
        payload = coerce_report_payload(payload)
    code, mid, why = validate_report_payload(home, payload)
    if code:
        op_raw = ""
        keys = ""
        if isinstance(payload, dict):
            op_raw = str(payload.get("op") or "")
            keys = ",".join(sorted(str(k) for k in payload.keys())[:12])
        peer_hint = ""
        print(f"INFO report reject {code} {why} op={op_raw!r} keys={keys}{peer_hint}", flush=True)
        return code, b""
    if rate is not None and not rate.allow("report:" + mid):
        print(f"INFO report reject 429 rate machine={mid}", flush=True)
        return 429, b""
    env = _enqueue_post(
        home,
        kind="report",
        payload=payload,
        headers=headers,
        meta={"op": str(payload.get("op") or "")},
    )
    eid = str(env.get("id") or "")
    try:
        out = bobreport.apply_callback(home, payload, briefer_nick)
    except bobreport.DigestLockBusy as exc:
        print(f"INFO report reject 503 digest.lock busy err={exc}", flush=True)
        if eid:
            webhook_queue.mark_done(home, eid, result={"ok": False, "err": "digest_lock_busy"})
        return 503, b'{"ok":false,"err":"digest_lock_busy"}'
    except Exception as exc:  # noqa: BLE001 — surface as 500 + failure intake
        _try_report_handler_failure(home, filer, route="report", err=str(exc))
        return 500, b""
    if not out.ok:
        op = str(payload.get("op") or "")
        _announce(home, f"REPORT fail op={op or '-'}")
        if eid:
            webhook_queue.mark_done(home, eid, result={"ok": False})
        return 400, b""
    if eid:
        webhook_queue.mark_done(home, eid, result={"ok": True, "changed": bool(out.changed)})
    if out.body is not None:
        return 200, out.body
    if not out.changed:
        return 200, b""
    return 204, b""


def handle_intake_post(
    headers: dict[str, str],
    body: bytes | str,
    home: Path,
    peer_ip: str,
    *,
    filer: intake.GitHubFiler | None = None,
    rate: intake.RateLimiter | None = None,
) -> tuple[int, bytes]:
    # Open endpoint: skill harvest / no-GitHub reporters must POST without a fleet secret.
    # No secret: rate limits + allowlist live in intake.process_intake.
    if len(body or b"") > MAX_BODY_BYTES:
        return 413, b'{"error":"too_large"}'
    payload = _parse_json_body(body, scan_secret=False)
    if payload is None:
        return 400, b'{"error":"invalid_json"}'
    env = _enqueue_post(home, kind="intake", payload=payload, headers=headers)
    eid = str(env.get("id") or "")
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    intake_key = (hdrs.get("x-bob-intake-key") or "").strip()
    use_filer: intake.GitHubFiler = filer or intake.FakeGitHubFiler()
    try:
        result = intake.process_intake(
            home,
            payload,
            filer=use_filer,
            client_ip=peer_ip or "0.0.0.0",
            intake_key_header=intake_key,
            rate=rate,
        )
    except Exception as exc:  # noqa: BLE001
        _try_report_handler_failure(home, use_filer, route="intake", err=str(exc))
        return 500, b'{"error":"handler_failure"}'
    if result.log_safe:
        _announce(home, result.log_safe)
    else:
        kind = str((payload or {}).get("kind") or "issue")
        _announce(home, f"INTAKE status={result.status} kind={kind}")
    if eid and result.status < 500:
        webhook_queue.mark_done(
            home,
            eid,
            result={"ok": result.status < 400, "status": result.status, "body": result.body},
        )
    body_out = json.dumps(result.body, separators=(",", ":")).encode("utf-8")
    return result.status, body_out


def handle_jira_post(
    headers: dict[str, str],
    body: bytes | str,
    home: Path,
    *,
    filer: intake.GitHubFiler | None = None,
    rate: intake.RateLimiter | None = None,
) -> tuple[int, bytes]:
    # Open endpoint: Jira Cloud/Data Center webhooks have no shared Bob secret.
    if len(body or b"") > MAX_BODY_BYTES:
        return 413, b""
    if rate is not None and not rate.allow("jira"):
        return 429, b""
    payload = _parse_json_body(body, scan_secret=False)
    if payload is None:
        return 400, b"invalid_json"
    env = _enqueue_post(home, kind="jira", payload=payload, headers=headers)
    eid = str(env.get("id") or "")
    try:
        lines, records, reject = jira_webhook.process_jira_webhook(payload, home=home)
    except Exception as exc:  # noqa: BLE001
        _try_report_handler_failure(home, filer, route="jira", err=str(exc))
        return 500, b""
    if reject:
        _announce(home, f"JIRA reject {reject}")
        if eid:
            webhook_queue.mark_done(home, eid, result={"ok": False, "reject": reject})
        return 400, reject.encode("utf-8")
    for line in lines:
        _announce(home, line)
    if not lines and records:
        _announce(home, f"JIRA updated count={len(records)}")
    if eid:
        webhook_queue.mark_done(
            home,
            eid,
            result={"ok": True, "count": len(records), "keys": [r.get("key") for r in records]},
        )
    return 204, b""


def handle_jira_get(home: Path, headers: dict[str, str]) -> tuple[int, bytes]:
    """GET tickets JSON; open (same policy as jira POST)."""
    _ = headers
    doc = jira_webhook.load_jira_tickets(home)
    tickets = doc.get("tickets") if isinstance(doc.get("tickets"), dict) else {}
    body = json.dumps(
        {"tickets": tickets, "updated_at": str(doc.get("updated_at") or "")},
        separators=(",", ":"),
    ).encode("utf-8")
    return 200, body


def handle_intake_status_get(home: Path, intake_id: str) -> tuple[int, bytes]:
    code, obj = intake.get_intake_status(home, intake_id)
    return code, json.dumps(obj, separators=(",", ":")).encode("utf-8")


def handle_request(
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes | str,
    peer_ip: str,
    home: Path,
    allow_ips: set[str] | None = None,
    briefer_nick: str = "",
    filer: intake.GitHubFiler | None = None,
    intake_rate: intake.RateLimiter | None = None,
    report_rate: intake.RateLimiter | None = None,
) -> tuple[int, bytes]:
    """Pure request handler. No sockets, no secret, no ChanServ. Public GET digest; POST validated."""
    verb = (method or "").upper()
    route = (path or "").split("?", 1)[0]
    # FR #1136: local health (lock age / digest writable); not the public IIS front-door.
    if verb in ("GET", "HEAD") and route == HEALTH_PATH:
        code, payload = handle_health_get(home)
        if verb == "HEAD":
            return code, b""
        return code, payload
    # GET/HEAD digest: local paths include /digest aliases; public front-door is REPORT_PATH only (#149).
    if verb in ("GET", "HEAD") and route in DIGEST_GET_PATHS:
        code, payload = handle_digest_get(home, briefer_nick)
        if verb == "HEAD":
            return code, b""
        return code, payload
    if verb in ("GET", "HEAD") and route == JIRA_PATH:
        code, payload = handle_jira_get(home, headers)
        if verb == "HEAD":
            return code, b""
        return code, payload
    if verb in ("GET", "HEAD") and route.startswith(INTAKE_PATH + "/"):
        iid = route[len(INTAKE_PATH) + 1 :].strip("/")
        if not iid or "/" in iid:
            return 404, b""
        code, payload = handle_intake_status_get(home, iid)
        if verb == "HEAD":
            return code, b""
        return code, payload
    # POST to digest-only aliases is not a write path.
    if route in (DIGEST_PATH, DIGEST_ALIAS):
        return 405, b""
    gate = _check_post_route(verb, route, peer_ip, allow_ips)
    if gate[0] != 0:
        return gate[0], gate[1]
    if route == GIT_WEBHOOK_PATH:
        return handle_git_webhook(headers, body, home, rate=report_rate)
    if route == INTAKE_PATH:
        return handle_intake_post(headers, body, home, peer_ip, filer=filer, rate=intake_rate)
    if route == JIRA_PATH:
        return handle_jira_post(headers, body, home, filer=filer, rate=report_rate)
    return handle_report_post(headers, body, home, briefer_nick, filer=filer, rate=report_rate)


class ReportHandler:
    """stdlib BaseHTTPRequestHandler mixin state. Instantiated by serve()."""

    home: Path
    allow_ips: set[str]
    briefer_nick: str


def _replay_handlers(
    home: Path,
    *,
    briefer_nick: str,
    filer: intake.GitHubFiler | None,
) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Build webhook_queue.process_pending handlers from durable envelopes."""

    def _report(env: dict[str, Any]) -> Any:
        payload = env.get("payload") if isinstance(env.get("payload"), dict) else {}
        out = bobreport.apply_callback(home, payload, briefer_nick)
        if not out.ok:
            raise RuntimeError("report_replay_failed")
        return {"changed": bool(out.changed)}

    def _git(env: dict[str, Any]) -> Any:
        payload = env.get("payload") if isinstance(env.get("payload"), dict) else {}
        meta = env.get("meta") if isinstance(env.get("meta"), dict) else {}
        headers = env.get("headers") if isinstance(env.get("headers"), dict) else {}
        event = str(meta.get("event") or headers.get("X-GitHub-Event") or headers.get("x-github-event") or "").strip()
        if not event:
            raise RuntimeError("git_replay_no_event")
        out = bobreport.apply_git_webhook(home, event, payload)
        if not out.ok:
            raise RuntimeError(out.err or "git_replay_failed")
        return {"announced": True}

    def _intake(env: dict[str, Any]) -> Any:
        payload = env.get("payload") if isinstance(env.get("payload"), dict) else {}
        use = filer or intake.FakeGitHubFiler()
        result = intake.process_intake(home, payload, filer=use, client_ip="127.0.0.1")
        if result.status >= 500:
            raise RuntimeError("intake_replay_failed")
        if result.log_safe:
            _announce(home, result.log_safe)
        return result.body

    def _jira(env: dict[str, Any]) -> Any:
        payload = env.get("payload") if isinstance(env.get("payload"), dict) else {}
        lines, records, reject = jira_webhook.process_jira_webhook(payload, home=home)
        if reject:
            raise RuntimeError(reject)
        for line in lines:
            _announce(home, line)
        return {"count": len(records)}

    return {"report": _report, "git": _git, "intake": _intake, "jira": _jira}


def drain_pending(
    home: Path,
    *,
    briefer_nick: str = "",
    filer: intake.GitHubFiler | None = None,
    limit: int = 20,
) -> list[str]:
    """Drain webhook_queue pending + intake outbox (when filer available)."""
    done = webhook_queue.process_pending(
        home,
        _replay_handlers(home, briefer_nick=briefer_nick, filer=filer),
        limit=limit,
    )
    if filer is not None:
        try:
            # FR #2595: same receipt-aware rules as CLI drain (probes drop, receipts
            # record-only, idempotent / intake/<iid> PR dedupe).
            stats = intake.drain_intake_outbox(home, filer, limit=limit)
            counts = getattr(stats, "as_counts", None)
            if callable(counts):
                c = counts()
                print(
                    "INFO intake_outbox_drain "
                    f"filed={c.get('filed')} receipt={c.get('recorded_receipt')} "
                    f"probe={c.get('dropped_probe')} dup={c.get('skipped_duplicate')} "
                    f"deferred={c.get('deferred')}",
                    flush=True,
                )
        except Exception:
            pass
    return done


def make_handler(
    home: Path,
    allow_ips: set[str],
    briefer_nick: str = "",
    filer: intake.GitHubFiler | None = None,
    intake_rate: intake.RateLimiter | None = None,
    report_rate: intake.RateLimiter | None = None,
):
    from http.server import BaseHTTPRequestHandler

    rate = intake_rate or intake.RateLimiter()
    rrate = report_rate or intake.RateLimiter(per_min=report_rate_per_min())

    class _Handler(BaseHTTPRequestHandler):
        def _run(self, method: str) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                self._reply(400, b"")
                return
            if length > MAX_BODY_BYTES:  # never read an oversized body into memory
                self._reply(413, b"")
                self.close_connection = True
                return
            body = self.rfile.read(length) if length > 0 else b""
            peer = (self.client_address or ("", 0))[0]
            code, payload = handle_request(
                method,
                self.path,
                {k: v for k, v in self.headers.items()},
                body,
                peer,
                home,
                allow_ips,
                briefer_nick,
                filer=filer,
                intake_rate=rate,
                report_rate=rrate,
            )
            self._reply(code, payload, method)

        def _reply(self, code: int, payload: bytes, method: str = "GET") -> None:
            self.send_response(code)
            if payload:
                ctype = "application/json; charset=utf-8"
                if self.path.split("?", 1)[0] == JIRA_PATH and method == "POST" and code == 400:
                    ctype = "text/plain; charset=utf-8"
                self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload and method != "HEAD":
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    # Client timed out while we waited on digest.lock / built the digest.
                    self.close_connection = True

        def do_GET(self) -> None:
            self._run("GET")

        def do_HEAD(self) -> None:
            self._run("HEAD")

        def do_POST(self) -> None:
            self._run("POST")

        def do_PUT(self) -> None:
            self._run("PUT")

        def log_message(self, _fmt: str, *_args: object) -> None:
            return

    return _Handler


def _health_watchdog_s() -> float:
    try:
        return max(5.0, float(os.environ.get(HEALTH_WATCHDOG_ENV) or DEFAULT_HEALTH_WATCHDOG_S))
    except ValueError:
        return DEFAULT_HEALTH_WATCHDOG_S


def _watchdog_try_break(home: Path, *, why: str) -> None:
    """FR #2902: break only when break_stale actually unlinks; log the real outcome."""
    holder = bobreport.digest_lock_holder_pid(home)
    age = bobreport.digest_lock_age_s(home)
    me = os.getpid()
    info = None
    with contextlib.suppress(Exception):
        info = bobreport.break_stale_digest_lock(home)
    if info:
        print(
            f"INFO health-watchdog broke digest.lock age={info.get('age')} "
            f"pid={info.get('pid')} reason={info.get('reason')} ({why})",
            flush=True,
        )
        return
    if holder is not None and int(holder) == int(me):
        print(
            f"WARN health-watchdog {why}; left own live digest.lock "
            f"pid={holder} age={age}",
            flush=True,
        )
        return
    print(
        f"WARN health-watchdog {why}; lock untouched holder={holder} age={age}",
        flush=True,
    )


def _start_health_watchdog(home: Path, host: str, port: int) -> None:
    """FR #1136 / #2902: periodic loopback /health; break stale/foreign lock on failure."""
    import threading
    import urllib.request

    interval = _health_watchdog_s()

    def _loop() -> None:
        url = f"http://{host}:{port}{HEALTH_PATH}"
        while True:
            try:
                time.sleep(interval)
            except Exception:
                return
            try:
                bobreport.break_stale_digest_lock(home)
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    raw = resp.read()
                doc = json.loads(raw.decode("utf-8") or "{}")
                if not doc.get("ok"):
                    print(f"WARN health-watchdog not-ok body={raw[:200]!r}", flush=True)
                    _watchdog_try_break(home, why="not-ok")
            except Exception as exc:  # noqa: BLE001 — heal and keep looping
                _watchdog_try_break(home, why=f"err={exc}")

    threading.Thread(target=_loop, name="bobcallback-health-watchdog", daemon=True).start()


def serve(
    home: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    allow_ips: set[str] | None = None,
    briefer_nick: str = "",
    filer: intake.GitHubFiler | None = None,
):
    """Blocking listener: public GET digest + validated, secret-free POST report/git/intake/jira."""
    from http.server import ThreadingHTTPServer

    listen_port = resolve_listen_port(int(port))
    # Loud, once: the roster is what Jeeves published (the receiver never asks ChanServ).
    roster = bobreport.roster_machine_ids(home)
    if roster:
        print(f"INFO report roster (published by Jeeves) machines={len(roster)}: {','.join(roster)}", flush=True)
    else:
        print(
            "WARN report roster EMPTY: registered-machines.json has no machines yet - machine POSTs to "
            "/bob/v1/report are refused (403) until Jeeves publishes the ChanServ roster",
            flush=True,
        )
    allow = allow_ips or load_allow_ips()
    use_filer = filer
    if use_filer is None:
        try:
            import gh_filer

            src = gh_filer.ensure_gh_token_env()
            print(f"INFO gh token source={src}", flush=True)
            use_filer = gh_filer.default_filer()
        except Exception:
            use_filer = None
    # Heal before accept: empty/stale/foreign digest.lock must not wedge the first requests.
    bobreport.break_stale_digest_lock(home)
    handler = make_handler(home, allow, briefer_nick, filer=use_filer)
    # FR #1388: bind :7700 BEFORE drain_pending. drain (webhook replay / intake outbox /
    # GitHub) can block for seconds while chair holds digest.lock — historically left
    # bobcallback.py alive with no LISTEN (SYN_SENT clients).
    httpd = ThreadingHTTPServer((host, listen_port), handler)
    _start_health_watchdog(home, host, listen_port)

    def _bg_drain() -> None:
        try:
            done = drain_pending(home, briefer_nick=briefer_nick, filer=use_filer)
            if done:
                print(f"INFO drain_pending done={len(done)}", flush=True)
        except Exception as exc:  # noqa: BLE001 — never kill the listener for drain
            print(f"WARN drain_pending err={exc}", flush=True)

    import threading

    threading.Thread(target=_bg_drain, name="bobcallback-drain", daemon=True).start()
    return httpd


def assert_home_usable(home: Path) -> None:
    """FR #1316: refuse to run when digest home is not writable (SYSTEM vs Admin wedge)."""
    import getpass

    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / f".bobcallback-write-probe.{os.getpid()}"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        print(f"ERROR home not writable path={home} err={exc}", flush=True)
        raise SystemExit(2) from exc
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or "?"
    print(f"INFO principal user={user} pid={os.getpid()} home={home}", flush=True)


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description=CLI_DESCRIPTION)
    p.add_argument("--home", default="", help="BOB_HOME (digest.json)")
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument(
        "--secret-file",
        default="",
        help="ignored (v0.1.16: webhooks need no secret); accepted so old scheduled tasks still start",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BOB_REPORT_PORT") or str(DEFAULT_PORT)),
        help=f"listen port (0 → BOB_REPORT_PORT or {DEFAULT_PORT}; never ephemeral)",
    )
    args = p.parse_args()
    home = Path(args.home).expanduser() if args.home else bobreport.digest_path(Path(".")).parent
    assert_home_usable(home)
    try:
        httpd = serve(home, host=args.bind, port=args.port)
    except OSError as exc:
        # Bind failure must be non-zero so Task Scheduler RestartCount can recover (FR #1316).
        print(f"ERROR bind failed host={args.bind} port={args.port} err={exc}", flush=True)
        raise SystemExit(1) from exc
    host, port = httpd.server_address[:2]
    print(
        f"INFO report listen {host}:{port} GET {REPORT_PATH}|{DIGEST_PATH}|{JIRA_PATH} "
        f"POST {REPORT_PATH} POST {GIT_WEBHOOK_PATH} POST {INTAKE_PATH} POST {JIRA_PATH}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
