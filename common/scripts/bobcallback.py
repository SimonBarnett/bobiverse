#!/usr/bin/env python3
"""Digest callback: report/git/intake/jira/hours/models; public GET digest (#174, #149).

Public IIS front-door GET is **/bob/v1/report** (FR #149 / FR #354) and **GET /jeeves**
login HTML (FR #6815). Local bobcallback also serves `/bob/v1/digest` and `/digest`
with the same JSON body; those aliases are not published through the bob.ntsa.uk IIS
rewrite today (GET https://bob.ntsa.uk/bob/v1/digest -> 404). GET **/bob/v1/models**
returns fleet agent Weights rows (BOB-01 / FR #8707). POST **/bob/v1/models/validate**
checks a ``(cli, model, context, effort)`` tuple against the fail-closed
``models-valid-combos.json`` allow-list (BOB-03 / FR #8710); it never persists.

Durable POST envelopes go through webhook_queue; chair announces on #bobiverse.

Report/intake/jira/hours stay open (no shared password header). Abuse protection:
body size caps (413), strict JSON-object + op/event schema validation, per-machine rate limiting
(429), GitHub hooks only for allow-listed owners, and POSTs on /bob/v1/report only from
machine ids on the roster that **Jeeves publishes** in ``registered-machines.json``.

FR #7467: when ``BOB_GIT_WEBHOOK_SECRET_FILE`` or ``<BOB_CONFIG_DIR>/github-webhook.secret``
exists, ``POST /bob/v1/git`` verifies ``X-Hub-Signature-256`` (HMAC-SHA256). With no secret file
the unsigned owner-gated contract is unchanged. Legacy CLI ``--secret-file`` stays ignored.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import bobhours
import bobreport
import builds_catalog
import intake
import jira_webhook
import models_catalog
import webhook_queue

REPORT_PATH = "/bob/v1/report"
JEEVES_LOGIN_PATH = "/jeeves"
GIT_WEBHOOK_PATH = "/bob/v1/git"
INTAKE_PATH = "/bob/v1/intake"
JIRA_PATH = "/bob/v1/jira"
HOURS_PATH = bobhours.HOURS_PATH
BUILDS_PATH = builds_catalog.BUILDS_PATH
MODELS_PATH = models_catalog.MODELS_PATH
MODELS_VALIDATE_PATH = models_catalog.MODELS_VALIDATE_PATH
DIGEST_PATH = "/bob/v1/digest"
HEALTH_PATH = "/health"
HEALTH_PROBE_ZEN = "jeeves-health-probe"
DIGEST_ALIAS = "/digest"
HEALTH_WATCHDOG_ENV = "BOB_CALLBACK_HEALTH_S"
DEFAULT_HEALTH_WATCHDOG_S = 30.0
# FR #7618: local GET must succeed within this budget or the self-probe counts a fail.
LISTENER_PROBE_ENV = "BOB_CALLBACK_LISTENER_PROBE_S"
DEFAULT_LISTENER_PROBE_S = 10.0
LISTENER_PROBE_FAILS_ENV = "BOB_CALLBACK_LISTENER_PROBE_FAILS"
DEFAULT_LISTENER_PROBE_FAILS = 2
LISTENER_EXIT_CODE = 1
# Public readers (IIS / browsers / UAT): use reportUrl. /bob/v1/digest is the same webhook and 301s here.
PUBLIC_DIGEST_PATH = REPORT_PATH
CLI_DESCRIPTION = (
    "POST /bob/v1/report|/bob/v1/git|/bob/v1/intake|/bob/v1/jira|/bob/v1/hours; "
    "front-door GET is /bob/v1/report|/jeeves (/bob/v1/digest 301s to /bob/v1/report); "
    "GET /bob/v1/jira; GET /bob/v1/builds; GET /bob/v1/models; GET|POST /bob/v1/hours"
)
ALLOW_ENV = "BOB_REPORT_ALLOW"
DEFAULT_PORT = 7700
# GET/HEAD/POST on these paths 301 to REPORT_PATH (same webhook; no duplicate handler).
DIGEST_REDIRECT_PATHS = frozenset({DIGEST_PATH, DIGEST_ALIAS})
# Public read paths (GET/HEAD). REPORT_PATH is also the write URL (POST).
DIGEST_GET_PATHS = frozenset({REPORT_PATH})
POST_ROUTES = frozenset(
    {REPORT_PATH, GIT_WEBHOOK_PATH, INTAKE_PATH, JIRA_PATH, HOURS_PATH}
)
PUT_ROUTES = frozenset({MODELS_PATH})  # BOB-02 / FR #8708
# Report/intake/jira stay open (no shared password). Git may optionally verify HMAC (FR #7467).
MAX_BODY_BYTES = 1024 * 1024          # hard cap for any POST body (413 above)
MAX_REPORT_BYTES = 256 * 1024         # /bob/v1/report bodies are tiny status docs
REPORT_RATE_ENV = "BOB_REPORT_RATE_PER_MIN"
DEFAULT_REPORT_RATE_PER_MIN = 120     # per machine id (tray posts ~2/min, workers a few more)
GIT_OWNERS_ENV = "BOB_GIT_OWNERS"     # comma list of GitHub owners whose hooks we accept
DEFAULT_GIT_OWNERS = ("SimonBarnett",)
GIT_RATE_PER_MIN = 120                # per repository
GIT_WEBHOOK_SECRET_FILE_ENV = "BOB_GIT_WEBHOOK_SECRET_FILE"
GIT_ALLOW_UNSIGNED_ENV = "BOB_GIT_ALLOW_UNSIGNED"
GIT_WEBHOOK_SECRET_NAME = "github-webhook.secret"
GIT_PROCESSING_RETRY_AFTER_S = "5"
# FR #4711 / #5170 / #7467: handled events (enqueue + apply). Others → 204 ignore after gates.
GIT_EVENTS = frozenset(
    {
        "ping",
        "push",
        "issues",
        "pull_request",
        "pull_request_review",
        "issue_comment",
        "check_run",
        "check_suite",
    }
)
# Subscribed but not applied (CI state comes from check_run + resync).
GIT_IGNORED_EVENTS = frozenset({"workflow_run"})
# FR #9104: under local intake rate limit, ack noisy CI storms with 204 (no GitHub retry)
# instead of 429. push / issues / PR keep 429 so GitHub backs off those.
GIT_RATE_DEFER_EVENTS = frozenset({"check_run", "check_suite"})
GIT_ERROR_REASONS = frozenset(
    {
        "missing signature",
        "invalid signature",
        "missing event header",
        "malformed JSON",
        "payload must be a JSON object",
        "missing repository",
        "owner not allowed",
        "body too large",
        "rate limited",
        "invalid content-length",
    }
)


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


def _is_allowed_post_route(route: str) -> bool:
    if route in POST_ROUTES:
        return True
    return bobhours.is_hours_post_route(route)


def _check_post_route(
    verb: str, route: str, peer_ip: str, allow_ips: set[str] | None
) -> tuple[int, set[str]] | tuple[int, bytes]:
    """Return (0, allow_set) on success, or (http_code, body) on failure."""
    allow = allow_ips if allow_ips is not None else load_allow_ips()
    if not _is_allowed_post_route(route):
        return 404, b""
    if verb != "POST":
        return 405, b""
    ip = (peer_ip or "").split("%", 1)[0]
    if allow and ip not in allow:
        return 403, b""
    return 0, allow




def _check_put_route(
    verb: str, route: str, peer_ip: str, allow_ips: set[str] | None
) -> tuple[int, set[str]] | tuple[int, bytes]:
    """BOB-02: PUT /bob/v1/models — unknown 404, wrong method 405, peer 403."""
    allow = allow_ips if allow_ips is not None else load_allow_ips()
    if route not in PUT_ROUTES:
        return 404, b""
    if verb != "PUT":
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


def git_webhook_secret_path() -> Path | None:
    """Prefer BOB_GIT_WEBHOOK_SECRET_FILE, else <BOB_CONFIG_DIR>/github-webhook.secret."""
    override = (os.environ.get(GIT_WEBHOOK_SECRET_FILE_ENV) or "").strip()
    if override:
        return Path(override)
    cfg = (os.environ.get("BOB_CONFIG_DIR") or "").strip()
    if cfg:
        return Path(cfg) / GIT_WEBHOOK_SECRET_NAME
    return None


def load_git_webhook_secret() -> str | None:
    """Return stripped secret bytes-as-str, or None when no file / empty. Never log the value."""
    path = git_webhook_secret_path()
    if path is None:
        return None
    try:
        if not path.is_file():
            return None
        val = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return val or None


def git_allow_unsigned() -> bool:
    return (os.environ.get(GIT_ALLOW_UNSIGNED_ENV) or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _git_error(reason: str, code: int = 400) -> tuple[int, bytes]:
    """Compact JSON 4xx for /bob/v1/git. Fixed vocabulary only; never echo secrets."""
    msg = reason if reason in GIT_ERROR_REASONS else "malformed JSON"
    body = json.dumps({"ok": False, "error": msg}, separators=(",", ":")).encode("utf-8")
    return code, body


def _git_deferred() -> tuple[int, bytes]:
    stash_response_headers([("Retry-After", GIT_PROCESSING_RETRY_AFTER_S)])
    return 503, json.dumps({"error": "processing deferred"}, separators=(",", ":")).encode("utf-8")


def verify_git_signature(body: bytes | str, headers: dict[str, str], secret: str) -> str | None:
    """Return None when OK, else a fixed reason: missing signature | invalid signature."""
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    raw_sig = (hdrs.get("x-hub-signature-256") or "").strip()
    if not raw_sig:
        return "missing signature"
    if not raw_sig.lower().startswith("sha256="):
        return "invalid signature"
    got = raw_sig.split("=", 1)[1].strip().lower()
    if len(got) != 64 or any(c not in "0123456789abcdef" for c in got):
        return "invalid signature"
    raw = body if isinstance(body, (bytes, bytearray)) else str(body or "").encode("utf-8")
    expect = hmac.new(secret.encode("utf-8"), bytes(raw), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, got):
        return "invalid signature"
    return None


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
        # FR #8103: lock-break / hold-exception counters so a storm is visible
        # without reading the Jeeves log.
        "lock_break_count": bobreport.digest_lock_break_count(),
        "lock_hold_exception_count": bobreport.digest_lock_hold_exception_count(),
    }
    return (200 if ok else 503), json.dumps(doc, separators=(",", ":")).encode("utf-8")

def _parse_json_body(body: bytes | str, *, scan_secret: bool = True) -> dict | None:
    """Parse JSON object. scan_secret=True rejects bodies that look like secrets (report path).

    Git webhooks must use scan_secret=False (FR #206): issue bodies may *mention*
    marker strings without being secrets; only the announce line is checked later.
    """
    payload, _err = _parse_json_body_reason(body, scan_secret=scan_secret)
    return payload


def _parse_json_body_reason(
    body: bytes | str, *, scan_secret: bool = True
) -> tuple[dict | None, str | None]:
    """Like _parse_json_body but returns a fixed reason when parsing fails."""
    if isinstance(body, bytes):
        raw = body.decode("utf-8", "replace")
    else:
        raw = body or ""
    if scan_secret and bobreport.looks_like_secret(raw):
        return None, "malformed JSON"
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None, "malformed JSON"
    if not isinstance(payload, dict):
        return None, "payload must be a JSON object"
    return payload, None


def _log_git_reject(
    reason: str,
    *,
    event: str = "",
    repo: str = "",
    number: str = "",
    marker: str = "",
    delivery: str = "",
) -> None:
    """One-line reject reason; marker *name* only, never a secret value."""
    bits = [f"reason={reason}"]
    if event:
        bits.append(f"event={event}")
    if repo:
        bits.append(f"repo={repo}")
    if number:
        bits.append(f"number={number}")
    if delivery:
        bits.append(f"delivery={delivery}")
    if marker:
        bits.append(f"marker={marker}")
    print("INFO git webhook reject " + " ".join(bits), flush=True)


def _log_git_ignore(
    reason: str,
    *,
    event: str = "",
    repo: str = "",
    delivery: str = "",
) -> None:
    bits = [f"reason={reason}"]
    if event:
        bits.append(f"event={event}")
    if repo:
        bits.append(f"repo={repo}")
    if delivery:
        bits.append(f"delivery={delivery}")
    print("INFO git webhook ignore " + " ".join(bits), flush=True)


def _safe_headers(headers: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    drop = {
        "x-bob-secret",
        "x-bob-intake-key",
        "authorization",
        "x-hub-signature",
        "x-hub-signature-256",
    }
    for k, v in (headers or {}).items():
        name = str(k)
        if name.lower() in drop:
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



def _ticket_closure_from_git(
    home: Path,
    event: str,
    payload: dict,
    *,
    delivery_id: str = "",
) -> None:
    """FR #6405: event-first close notices (same pending/seen/wake as the poller)."""
    try:
        import ticket_closure as tc
    except ImportError:
        import sys

        mon = Path(__file__).resolve().parents[2] / "jeeves" / "tools" / "monitor"
        if mon.is_dir() and str(mon) not in sys.path:
            sys.path.insert(0, str(mon))
        import ticket_closure as tc  # noqa: E402
    tc.ingest_github_webhook(home, event, payload, delivery_id=delivery_id)


def handle_git_webhook(
    headers: dict[str, str],
    body: bytes | str,
    home: Path,
    *,
    envelope_id: str | None = None,
    rate: intake.RateLimiter | None = None,
) -> tuple[int, bytes]:
    """FR #7467: HMAC (when secret provisioned), 8 handled events, ignore+204 others."""
    stash_response_headers([])
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    delivery = (hdrs.get("x-github-delivery") or "").strip()[:80]
    raw = body if isinstance(body, (bytes, bytearray)) else str(body or "").encode("utf-8")
    if len(raw) > MAX_BODY_BYTES:
        _log_git_reject("body too large", delivery=delivery)
        return _git_error("body too large", 413)

    secret = load_git_webhook_secret()
    if secret:
        sig_err = verify_git_signature(raw, headers, secret)
        if sig_err == "missing signature" and git_allow_unsigned():
            _log_git_reject("unsigned accepted", delivery=delivery)
        elif sig_err:
            _log_git_reject(sig_err, delivery=delivery)
            return _git_error(sig_err, 401)

    event = (hdrs.get("x-github-event") or "").strip()
    if not event:
        _log_git_reject("missing event header", delivery=delivery)
        return _git_error("missing event header", 400)

    payload, parse_err = _parse_json_body_reason(raw, scan_secret=False)
    if payload is None:
        _log_git_reject(parse_err or "malformed JSON", event=event, delivery=delivery)
        return _git_error(parse_err or "malformed JSON", 400)

    full = bobreport._github_repo_name(payload)  # noqa: SLF001
    owner, _, name = full.partition("/")
    if not owner or not name:
        _log_git_reject("missing repository", event=event, delivery=delivery)
        return _git_error("missing repository", 400)
    if owner.lower() not in git_owners():
        _log_git_reject("owner not allowed", event=event, repo=full[:80], delivery=delivery)
        return _git_error("owner not allowed", 403)

    ev = event.lower()
    if ev == "ping" and str(payload.get("zen") or "") == HEALTH_PROBE_ZEN:
        return 204, b""

    if ev not in GIT_EVENTS:
        reason = "ignored event"
        if ev in GIT_IGNORED_EVENTS:
            reason = "ignored workflow_run" if ev == "workflow_run" else f"ignored {ev}"
        _log_git_ignore(reason, event=event, repo=full[:80], delivery=delivery)
        return 204, b""

    if rate is not None and not rate.allow("git:" + full.lower()):
        # FR #9104: check_run/check_suite storms → 204 ignore (GitHub does not retry);
        # keep 429 for push/PR/issues so delivery backs off.
        if ev in GIT_RATE_DEFER_EVENTS:
            _log_git_ignore(
                "rate deferred", event=event, repo=full[:80], delivery=delivery
            )
            return 204, b""
        _log_git_reject("rate limited", event=event, repo=full[:80], delivery=delivery)
        return _git_error("rate limited", 429)

    eid = ""
    try:
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
            number = ""
            issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else None
            pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else None
            ent = issue or pr
            if isinstance(ent, dict) and ent.get("number") is not None:
                number = str(ent.get("number"))
            _log_git_reject(out.err or "error", event=event, repo=full[:80], number=number, delivery=delivery)
            if out.err in ("no event", "malformed"):
                if eid:
                    webhook_queue.mark_done(home, eid, result={"ok": False, "err": out.err})
                return _git_error("malformed JSON" if out.err == "malformed" else "missing event header", 400)
            # State may already be written; announce-line refusal is not a client error.
            if out.err == "announce":
                if eid:
                    webhook_queue.mark_done(home, eid, result={"ok": True, "announce": False})
                _log_git_ignore("announce skipped", event=event, repo=full[:80], delivery=delivery)
                return 204, b""
            _announce(home, f"GIT fail event={event} err={out.err or 'error'}")
            return _git_deferred()
        if eid:
            webhook_queue.mark_done(home, eid, result={"ok": True})
    except Exception as exc:  # noqa: BLE001 - keep envelope pending for drain
        _log_git_reject(
            f"processing exception type={type(exc).__name__}",
            event=event,
            repo=full[:80],
            delivery=delivery,
        )
        with contextlib.suppress(Exception):
            _announce(home, f"GIT fail event={event} err=processing deferred")
        return _git_deferred()

    if ev in {"issues", "pull_request"}:
        try:
            _ticket_closure_from_git(
                home,
                event,
                payload,
                delivery_id=delivery,
            )
        except Exception:  # noqa: BLE001
            pass
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
    FR #7347: normalize ``needs-sign-in`` -> ``needs_sign_in`` before schema check.
    """
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    if "state" in out and out.get("state") not in (None, ""):
        out["state"] = bobreport.normalize_worker_state(out.get("state"))
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
        st_n = bobreport.normalize_worker_state(st) if st not in (None, "") else ""
        if st_n and st_n not in bobreport.WORKER_STATES:
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
        # FR #7347: short error body (no secrets) so seats can log a truncated snippet.
        err = str(why or "rejected").strip()[:80] or "rejected"
        return code, json.dumps({"error": err}, separators=(",", ":")).encode("utf-8")
    if rate is not None and not rate.allow("report:" + mid):
        print(f"INFO report reject 429 rate machine={mid}", flush=True)
        return 429, json.dumps({"error": "rate limited"}, separators=(",", ":")).encode("utf-8")
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


# FR #7274: bobcallback HTTP layer only returns (code, body); stash hop-by-hop
# response headers (Set-Cookie, Content-Type) so public /jeeves login sessions work.
_RESPONSE_EXTRA_HEADERS: list[tuple[str, str]] = []


def stash_response_headers(headers: list[tuple[str, str]] | None) -> None:
    """Replace the per-request extra header stash (cleared by pop)."""
    global _RESPONSE_EXTRA_HEADERS
    _RESPONSE_EXTRA_HEADERS = list(headers or [])


def pop_response_headers() -> list[tuple[str, str]]:
    """Return and clear stashed response headers for the HTTP _reply path."""
    global _RESPONSE_EXTRA_HEADERS
    out = list(_RESPONSE_EXTRA_HEADERS)
    _RESPONSE_EXTRA_HEADERS = []
    return out


def _headers_from_urlopen(resp: Any) -> list[tuple[str, str]]:
    """Copy Set-Cookie (multi) + Content-Type from an urlopen / HTTPError response."""
    out: list[tuple[str, str]] = []
    raw = getattr(resp, "headers", None)
    if raw is None:
        return out
    get_all = getattr(raw, "get_all", None)
    if callable(get_all):
        for cookie in get_all("Set-Cookie") or []:
            out.append(("Set-Cookie", str(cookie)))
    else:
        one = raw.get("Set-Cookie")
        if one:
            out.append(("Set-Cookie", str(one)))
    ctype = raw.get("Content-Type")
    if ctype:
        out.append(("Content-Type", str(ctype)))
    return out


def _proxy_jeeves_settings(
    method: str,
    route: str,
    headers: dict[str, str],
    body: bytes | str,
) -> tuple[int, bytes] | None:
    """FR #7274: forward /jeeves* to the LAN settings server (default 127.0.0.1:7701).

    Stashes upstream Set-Cookie + Content-Type via stash_response_headers so the
    bobcallback HTTP _reply can emit them (handle_request stays (code, body)).
    """
    base = (os.environ.get("JEEVES_SETTINGS_UPSTREAM") or "http://127.0.0.1:7701").rstrip("/")
    url = base + route
    raw = body if isinstance(body, (bytes, bytearray)) else str(body or "").encode("utf-8")
    hdrs = {}
    for key, val in (headers or {}).items():
        lk = str(key or "").lower()
        if lk in ("host", "content-length"):
            continue
        if lk in ("cookie", "content-type", "authorization", "x-forwarded-for", "x-forwarded-proto"):
            hdrs[key] = val
    req = Request(url, data=raw if method.upper() not in ("GET", "HEAD") else None, method=method.upper(), headers=hdrs)
    # FR #7527: a real AD logon can take longer than the 8s webhook proxy budget.
    # A timeout used to fall through to a bare 404 with no JSON error.
    login_post = method.upper() == "POST" and route.rstrip("/").endswith("/api/login")
    timeout = 30 if login_post else 8
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = resp.read() if method.upper() != "HEAD" else b""
            stash_response_headers(_headers_from_urlopen(resp))
            return int(getattr(resp, "status", 200) or 200), payload
    except HTTPError as exc:
        try:
            payload = exc.read() if method.upper() != "HEAD" else b""
        except Exception:
            payload = b""
        stash_response_headers(_headers_from_urlopen(exc))
        return int(exc.code or 502), payload
    except (URLError, TimeoutError, OSError) as exc:
        if method.upper() in ("GET", "HEAD"):
            return None
        err = type(exc).__name__
        payload = json.dumps(
            {"ok": False, "error": f"settings upstream unavailable: {err}"},
            separators=(",", ":"),
        ).encode("utf-8")
        stash_response_headers([("Content-Type", "application/json; charset=utf-8")])
        return 502, payload


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
    stash_response_headers([])
    verb = (method or "").upper()
    route = (path or "").split("?", 1)[0]
    # FR #6815 / #7274: public /jeeves* on bob.ntsa.uk (IIS rewrite to this process).
    if route == JEEVES_LOGIN_PATH or route.startswith(JEEVES_LOGIN_PATH + "/"):
        import jeeves_settings_http as _jhttp

        if verb in ("GET", "HEAD"):
            prefix, inner = _jhttp.split_ui_path(route)
            if inner in ("/login",) or route == JEEVES_LOGIN_PATH:
                html = _jhttp._render_login_html(prefix="/jeeves")
                payload = html.encode("utf-8")
                stash_response_headers([("Content-Type", "text/html; charset=utf-8")])
                if verb == "HEAD":
                    return 200, b""
                return 200, payload
            # FR #7454: commands reference is public — never proxy behind settings login.
            if inner in ("/commands", "/commands/"):
                data = _jhttp.load_jeeves_commands_html()
                if data is None:
                    return 404, b""
                stash_response_headers([("Content-Type", "text/html; charset=utf-8")])
                return (200, b"") if verb == "HEAD" else (200, data)
            if inner == _jhttp.BUTLER_HREF:
                p = _jhttp.butler_ico_path()
                if p.is_file():
                    data = p.read_bytes()
                    stash_response_headers([("Content-Type", "image/x-icon")])
                    return (200, b"") if verb == "HEAD" else (200, data)
                return 404, b""
            if inner == _jhttp.LOGO_HREF:
                p = _jhttp.ntsa_gut_logo_path()
                if p.is_file():
                    data = p.read_bytes()
                    stash_response_headers([("Content-Type", "image/png")])
                    return (200, b"") if verb == "HEAD" else (200, data)
                return 404, b""
        proxied = _proxy_jeeves_settings(verb, route, headers, body)
        if proxied is not None:
            return proxied
        if verb in ("GET", "HEAD") and (route == JEEVES_LOGIN_PATH or route.rstrip("/") == JEEVES_LOGIN_PATH):
            import jeeves_settings_http as _jhttp2

            html = _jhttp2._render_login_html(prefix="/jeeves")
            payload = html.encode("utf-8")
            stash_response_headers([("Content-Type", "text/html; charset=utf-8")])
            return (200, b"") if verb == "HEAD" else (200, payload)
        return 404, b""
    # FR #1136: local health (lock age / digest writable); not the public IIS front-door.
    if verb in ("GET", "HEAD") and route == HEALTH_PATH:
        code, payload = handle_health_get(home)
        if verb == "HEAD":
            return code, b""
        return code, payload
    # /bob/v1/digest and /digest are the same webhook as /bob/v1/report — permanent redirect.
    if route in DIGEST_REDIRECT_PATHS:
        stash_response_headers([("Location", REPORT_PATH)])
        return 301, b""
    # GET/HEAD fleet digest JSON (canonical path).
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
    # FR #8490: buildable catalog for numbered !build (static builds-catalog.json).
    if verb in ("GET", "HEAD") and route == BUILDS_PATH:
        code, payload = builds_catalog.handle_builds_get(home)
        stash_response_headers([("Content-Type", "application/json; charset=utf-8")])
        if verb == "HEAD":
            return code, b""
        return code, payload
    # BOB-01 / FR #8707: fleet agent Weights rows (models-catalog.json or built-in defaults).
    if verb in ("GET", "HEAD") and route == MODELS_PATH:
        code, payload = models_catalog.handle_models_get(home)
        stash_response_headers([("Content-Type", "application/json; charset=utf-8")])
        if verb == "HEAD":
            return code, b""
        return code, payload
    # BOB-02 / FR #8708: PUT replace Weights (PATCH stays 501 via BaseHTTPRequestHandler).
    if route == MODELS_PATH:
        if verb == "PUT":
            gate = _check_put_route(verb, route, peer_ip, allow_ips)
            if gate[0] != 0:
                return gate[0], gate[1]
            code, payload = models_catalog.handle_models_put(body, home)
            if code in (200, 400, 413, 500, 503) and payload:
                stash_response_headers([("Content-Type", "application/json; charset=utf-8")])
            return code, payload
        if verb in ("POST", "DELETE"):
            return 405, b""
    if verb in ("GET", "HEAD") and route.startswith(INTAKE_PATH + "/"):
        iid = route[len(INTAKE_PATH) + 1 :].strip("/")
        if not iid or "/" in iid:
            return 404, b""
        code, payload = handle_intake_status_get(home, iid)
        if verb == "HEAD":
            return code, b""
        return code, payload
    # FR #3450: hours list/summary/export (no auth; schema + size + rate on writes).
    if verb in ("GET", "HEAD") and bobhours.is_hours_route(route):
        hours_rate = report_rate or intake.RateLimiter(per_min=bobhours.hours_rate_per_min())
        code, payload, _ctype = bobhours.handle_hours_request(
            verb, path, body, home, peer_ip=peer_ip, rate=hours_rate
        )
        if verb == "HEAD":
            return code, b""
        return code, payload
    gate = _check_post_route(verb, route, peer_ip, allow_ips)
    if gate[0] != 0:
        return gate[0], gate[1]
    if bobhours.is_hours_post_route(route):
        hours_rate = report_rate or intake.RateLimiter(per_min=bobhours.hours_rate_per_min())
        code, payload, _ctype = bobhours.handle_hours_request(
            verb, path, body, home, peer_ip=peer_ip, rate=hours_rate
        )
        return code, payload
    if route == GIT_WEBHOOK_PATH:
        return handle_git_webhook(headers, body, home, rate=report_rate)
    if route == INTAKE_PATH:
        return handle_intake_post(headers, body, home, peer_ip, filer=filer, rate=intake_rate)
    if route == JIRA_PATH:
        return handle_jira_post(headers, body, home, filer=filer, rate=report_rate)
    # No POST /bob/v1/models/validate — Weights form dropdowns are the validation (Si 2026-11-22).
    if route == MODELS_VALIDATE_PATH:
        stash_response_headers([("Content-Type", "application/json; charset=utf-8")])
        return 404, b'{"error":"no_models_validate","hint":"use GET /bob/v1/models catalog; Weights form validates"}'
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
            stats = intake.drain_intake_outbox_all(home, filer, batch=limit)
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
            route = (self.path or "").split("?", 1)[0]
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                if route == GIT_WEBHOOK_PATH:
                    self._reply(400, _git_error("invalid content-length", 400)[1])
                else:
                    self._reply(400, b"")
                return
            if length > MAX_BODY_BYTES:  # never read an oversized body into memory
                if route == GIT_WEBHOOK_PATH:
                    self._reply(413, _git_error("body too large", 413)[1])
                else:
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
            extra = pop_response_headers()
            ctype_from_extra = ""
            for hk, hv in extra:
                if str(hk).lower() == "content-type":
                    ctype_from_extra = str(hv)
                    continue
                self.send_header(hk, hv)
            if payload or ctype_from_extra:
                ctype = ctype_from_extra or "application/json; charset=utf-8"
                if not ctype_from_extra:
                    route = self.path.split("?", 1)[0]
                    if (route.rstrip("/") or "/") == JEEVES_LOGIN_PATH:
                        ctype = "text/html; charset=utf-8"
                    elif route == JIRA_PATH and method == "POST" and code == 400:
                        ctype = "text/plain; charset=utf-8"
                    elif (
                        route == HOURS_PATH + "/export"
                        and "format=csv" in (self.path or "").lower()
                        and code == 200
                    ):
                        ctype = "text/csv; charset=utf-8"
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


def _listener_probe_s() -> float:
    """FR #7618: seconds allowed for a local GET before the probe counts a failure."""
    try:
        return max(1.0, float(os.environ.get(LISTENER_PROBE_ENV) or DEFAULT_LISTENER_PROBE_S))
    except ValueError:
        return DEFAULT_LISTENER_PROBE_S


def _listener_probe_max_fails() -> int:
    try:
        return max(1, int(os.environ.get(LISTENER_PROBE_FAILS_ENV) or DEFAULT_LISTENER_PROBE_FAILS))
    except ValueError:
        return DEFAULT_LISTENER_PROBE_FAILS


def probe_listener_local_get(url: str, timeout_s: float) -> dict[str, Any]:
    """FR #7618: one loopback GET; raises on timeout / transport failure."""
    import urllib.request

    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
        raw = resp.read()
    doc = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(doc, dict):
        raise RuntimeError("listener probe: non-object JSON")
    return doc


def report_http_listener_fault(
    *,
    why: str,
    detail: str = "",
    host: str = "",
    port: int = 0,
    exc: BaseException | None = None,
    report_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """FR #7618: one intake/crash report for accept/serve or self-probe failure. No secrets."""
    if report_fn is not None:
        return report_fn(
            why=why,
            detail=detail,
            host=host,
            port=port,
            exc_type=type(exc).__name__ if exc else "",
        )
    title = "bug: Jeeves HTTP listener fault (FR #7618)"
    exc_name = type(exc).__name__ if exc else ""
    body = (
        "What: the HTTP accept/serve loop or local self-probe failed; the process "
        "exits non-zero so the service manager can restart (FR #7618).\n"
        f"Where: bobcallback/jeeves-http host={host or '-'} port={port or 0}\n"
        f"Evidence: why={why} exc={exc_name} detail={str(detail or '')[:400]}\n"
        "Fix: inspect memory pressure / accept path; do not leave the port bound but dead.\n"
        "No secrets."
    )
    if os.environ.get("PYTEST_CURRENT_TEST") and report_fn is None:
        return {"ok": True, "skipped": True, "reason": "pytest"}
    try:
        import crash_report

        if exc is not None:
            return crash_report.report_exception(
                "jeeves",
                type(exc),
                exc,
                exc.__traceback__,
                repo="SimonBarnett/bobiverse",
            )
        return crash_report._post_intake(
            title,
            body,
            repo="SimonBarnett/bobiverse",
            sig=f"http-listener-fault|{why}|{host}|{port}"[:128],
            exe="jeeves",
        )
    except Exception:
        return {"ok": False, "why": why}


def listener_self_probe_tick(
    *,
    host: str,
    port: int,
    timeout_s: float,
    fail_streak: int,
    max_fails: int,
    report_fn: Callable[..., dict[str, Any]] | None = None,
    exit_fn: Callable[[int], None] | None = None,
    path: str = HEALTH_PATH,
) -> int:
    """FR #7618: one self-probe tick. Returns updated fail streak; may call exit_fn(nonzero)."""
    url = f"http://{host}:{int(port)}{path}"
    try:
        doc = probe_listener_local_get(url, float(timeout_s))
        if not doc.get("ok", True):
            raise RuntimeError(f"listener probe not-ok body_keys={list(doc)[:8]}")
        return 0
    except Exception as exc:  # noqa: BLE001 — probe failure is the signal
        streak = int(fail_streak) + 1
        print(
            f"WARN listener-self-probe fail streak={streak}/{max_fails} "
            f"err={type(exc).__name__}: {exc}",
            flush=True,
        )
        if streak < max(1, int(max_fails)):
            return streak
        try:
            report_http_listener_fault(
                why="self-probe",
                detail=str(exc)[:400],
                host=host,
                port=int(port),
                exc=exc,
                report_fn=report_fn,
            )
        except Exception:
            pass
        print(
            f"ERROR listener-self-probe giving up after {streak} fails; "
            f"exit={LISTENER_EXIT_CODE} (FR #7618)",
            flush=True,
        )
        if exit_fn is not None:
            exit_fn(LISTENER_EXIT_CODE)
        else:
            os._exit(LISTENER_EXIT_CODE)
        return streak


def serve_forever_guarded(
    httpd,
    *,
    report_fn: Callable[[BaseException], None] | None = None,
    exit_fn: Callable[[int], None] | None = None,
) -> None:
    """FR #7618: wrap serve_forever so accept/serve fatals never leave a silent dead listener.

    On MemoryError or any unexpected exception leaving serve_forever: report, close the
    socket, and exit non-zero so NSSM / Task Scheduler restarts the process. Clean
    shutdown (shutdown_request / KeyboardInterrupt) returns normally.
    """

    def _report(exc: BaseException) -> None:
        if report_fn is not None:
            report_fn(exc)
            return
        report_http_listener_fault(
            why="accept-serve",
            detail=str(exc)[:400],
            host=str(getattr(httpd, "server_address", ("", 0))[0] or ""),
            port=int(getattr(httpd, "server_address", ("", 0))[1] or 0),
            exc=exc,
        )

    def _exit(code: int) -> None:
        if exit_fn is not None:
            exit_fn(int(code))
            return
        os._exit(int(code))

    while True:
        try:
            httpd.serve_forever()
            return
        except KeyboardInterrupt:
            return
        except SystemExit:
            raise
        except BaseException as exc:  # noqa: BLE001 — MemoryError must not kill only the thread
            print(
                f"ERROR http accept/serve fatal {type(exc).__name__}: {exc} (FR #7618)",
                flush=True,
            )
            try:
                _report(exc)
            except Exception:
                pass
            with contextlib.suppress(Exception):
                httpd.server_close()
            _exit(LISTENER_EXIT_CODE)
            return


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


def _httpd_shut_down(httpd) -> bool:
    """True after BaseServer.serve_forever has left (shutdown or socket close).

    The private event is created on the first serve_forever and set in its
    finally. Before that call it does not exist, so a live process that has
    not started accept yet is not treated as stopped.
    """
    ev = getattr(httpd, "_BaseServer__is_shut_down", None)
    return ev is not None and ev.is_set()


def _start_health_watchdog(home: Path, host: str, port: int, httpd) -> None:
    """FR #1136 / #2902 / #7618: loopback /health; break stale lock; exit if probe stays dead.

    FR #7657: once the caller has shut the server down, leave the process
    alone. Tests (and any embed) call serve() then shutdown(); the old loop
    kept probing the dead port and os._exit'd the whole interpreter, so
    pytest died with no failure summary.
    """
    import threading

    interval = _health_watchdog_s()
    probe_budget = _listener_probe_s()
    max_fails = _listener_probe_max_fails()

    def _exit_unless_stopped(code: int) -> None:
        if _httpd_shut_down(httpd):
            return
        os._exit(int(code))

    def _loop() -> None:
        fail_streak = 0
        while True:
            try:
                time.sleep(interval)
            except Exception:
                return
            if _httpd_shut_down(httpd):
                return
            with contextlib.suppress(Exception):
                bobreport.break_stale_digest_lock(home)
            # FR #7618: self-probe with explicit budget; consecutive fails → report + exit.
            fail_streak = listener_self_probe_tick(
                host=host,
                port=int(port),
                timeout_s=probe_budget,
                fail_streak=fail_streak,
                max_fails=max_fails,
                exit_fn=_exit_unless_stopped,
            )
            if _httpd_shut_down(httpd):
                return
            if fail_streak == 0:
                continue
            # Still below max_fails: keep digest.lock heal behaviour from FR #1136.
            _watchdog_try_break(home, why=f"probe-fail-streak={fail_streak}")

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
    _start_health_watchdog(home, host, listen_port, httpd)

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
    # BOB-04 / FR #8709: seed models-valid-combos.json before serving validate.
    try:
        import models_catalog as _models_catalog

        _models_catalog.ensure_valid_combos_seeded(home)
    except Exception as exc:  # noqa: BLE001 - never block listen on seed faults
        print(f"WARN models-valid-combos seed skipped err={exc}", flush=True)
    try:
        httpd = serve(home, host=args.bind, port=args.port)
    except OSError as exc:
        # Bind failure must be non-zero so Task Scheduler RestartCount can recover (FR #1316).
        print(f"ERROR bind failed host={args.bind} port={args.port} err={exc}", flush=True)
        raise SystemExit(1) from exc
    host, port = httpd.server_address[:2]
    print(
        f"INFO report listen {host}:{port} GET {REPORT_PATH}|{DIGEST_PATH}|{JIRA_PATH}|{BUILDS_PATH}|{MODELS_PATH}|{HOURS_PATH} "
        f"PUT {MODELS_PATH} "
        f"POST {REPORT_PATH} POST {GIT_WEBHOOK_PATH} POST {INTAKE_PATH} POST {JIRA_PATH} POST {HOURS_PATH} "
        f"POST {MODELS_VALIDATE_PATH}",
        flush=True,
    )
    try:
        # FR #7618: never leave :port bound but dead after accept/serve MemoryError.
        serve_forever_guarded(httpd)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
