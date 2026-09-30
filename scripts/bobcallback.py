#!/usr/bin/env python3
"""Digest callback: report/git/intake/jira; public GET digest (#174).

GET/HEAD on /bob/v1/report returns the JSON digest (same body as /bob/v1/digest).
IIS already proxies reportUrl; browsers must not keep seeing 405.

Durable POST envelopes go through webhook_queue; chair announces on #bobiverse.
"""
from __future__ import annotations

import json
import os
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
DIGEST_ALIAS = "/digest"
SECRET_ENV = "BOB_REPORT_SECRET"
ALLOW_ENV = "BOB_REPORT_ALLOW"
DEFAULT_PORT = 7700
# Public read paths (GET/HEAD). REPORT_PATH is also the write URL (POST).
DIGEST_GET_PATHS = frozenset({DIGEST_PATH, DIGEST_ALIAS, REPORT_PATH})
POST_ROUTES = frozenset({REPORT_PATH, GIT_WEBHOOK_PATH, INTAKE_PATH, JIRA_PATH})
# Report stays secret-gated. Intake + jira are open (skill/harvest reporters; Jira webhooks).
SECRET_POST_ROUTES = frozenset({REPORT_PATH})


def secret_path() -> Path:
    return Path.home() / ".grok" / "bob" / "report.secret"


def load_secret() -> str:
    env = (os.environ.get(SECRET_ENV) or "").strip()
    if env:
        return env
    path = secret_path()
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


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


def _secret_matches(headers: dict[str, str], secret: str) -> bool:
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    got = (hdrs.get("x-bob-secret") or "").strip()
    return bool(secret) and got == secret


def _announce(home: Path, text: str) -> bool:
    return bobreport.enqueue_chair_fleet_privmsg(home, text)


def handle_digest_get(home: Path, briefer_nick: str = "") -> tuple[int, bytes]:
    """Public readable digest (#174). No secret; nothing in digest is secure."""
    briefer = (briefer_nick or "").strip() or "digest"
    doc = bobreport.build_digest_object(home, briefer)
    body = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    return 200, body


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
) -> tuple[int, bytes]:
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    event = (hdrs.get("x-github-event") or "").strip()
    if not event:
        _log_git_reject("no event")
        return 400, b""
    # Do not secret-scan the full JSON (FR #206).
    payload = _parse_json_body(body, scan_secret=False)
    if payload is None:
        _log_git_reject("invalid json", event=event)
        return 400, b""
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


def handle_report_post(
    headers: dict[str, str],
    body: bytes | str,
    home: Path,
    secret: str,
    briefer_nick: str = "",
    *,
    filer: intake.GitHubFiler | None = None,
) -> tuple[int, bytes]:
    if not _secret_matches(headers, secret):
        return 401, b""
    payload = _parse_json_body(body)
    if payload is None:
        return 400, b""
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
    secret: str,
    peer_ip: str,
    *,
    filer: intake.GitHubFiler | None = None,
    rate: intake.RateLimiter | None = None,
) -> tuple[int, bytes]:
    # Open endpoint: skill harvest / no-GitHub reporters must POST without a fleet secret.
    # Optional X-Bob-Secret is ignored; rate limits + allowlist live in intake.process_intake.
    _ = secret
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
    secret: str,
    *,
    filer: intake.GitHubFiler | None = None,
) -> tuple[int, bytes]:
    # Open endpoint: Jira Cloud/Data Center webhooks have no shared Bob secret.
    _ = secret
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


def handle_jira_get(home: Path, headers: dict[str, str], secret: str) -> tuple[int, bytes]:
    """GET tickets JSON; open (same policy as jira POST)."""
    _ = headers, secret
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
    secret: str,
    allow_ips: set[str] | None = None,
    briefer_nick: str = "",
    filer: intake.GitHubFiler | None = None,
    intake_rate: intake.RateLimiter | None = None,
) -> tuple[int, bytes]:
    """Pure request handler. No sockets. Public GET digest; POST still gated."""
    verb = (method or "").upper()
    route = (path or "").split("?", 1)[0]
    # GET/HEAD digest on /bob/v1/digest, /digest, and reportUrl (/bob/v1/report).
    if verb in ("GET", "HEAD") and route in DIGEST_GET_PATHS:
        code, payload = handle_digest_get(home, briefer_nick)
        if verb == "HEAD":
            return code, b""
        return code, payload
    if verb in ("GET", "HEAD") and route == JIRA_PATH:
        code, payload = handle_jira_get(home, headers, secret)
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
        return handle_git_webhook(headers, body, home)
    if route == INTAKE_PATH:
        return handle_intake_post(
            headers, body, home, secret, peer_ip, filer=filer, rate=intake_rate
        )
    if route == JIRA_PATH:
        return handle_jira_post(headers, body, home, secret, filer=filer)
    return handle_report_post(headers, body, home, secret, briefer_nick, filer=filer)


class ReportHandler:
    """stdlib BaseHTTPRequestHandler mixin state. Instantiated by serve()."""

    home: Path
    secret: str
    allow_ips: set[str]
    briefer_nick: str


def _replay_handlers(
    home: Path,
    *,
    secret: str,
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
    secret: str = "",
    briefer_nick: str = "",
    filer: intake.GitHubFiler | None = None,
    limit: int = 20,
) -> list[str]:
    """Drain webhook_queue pending + intake outbox (when filer available)."""
    done = webhook_queue.process_pending(
        home,
        _replay_handlers(home, secret=secret, briefer_nick=briefer_nick, filer=filer),
        limit=limit,
    )
    if filer is not None:
        try:
            intake.drain_intake_outbox(home, filer, limit=limit)
        except Exception:
            pass
    return done


def make_handler(
    home: Path,
    secret: str,
    allow_ips: set[str],
    briefer_nick: str = "",
    filer: intake.GitHubFiler | None = None,
    intake_rate: intake.RateLimiter | None = None,
):
    from http.server import BaseHTTPRequestHandler

    rate = intake_rate or intake.RateLimiter()

    class _Handler(BaseHTTPRequestHandler):
        def _run(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            peer = (self.client_address or ("", 0))[0]
            code, payload = handle_request(
                method,
                self.path,
                {k: v for k, v in self.headers.items()},
                body,
                peer,
                home,
                secret,
                allow_ips,
                briefer_nick,
                filer=filer,
                intake_rate=rate,
            )
            self.send_response(code)
            if payload:
                ctype = "application/json; charset=utf-8"
                if self.path.split("?", 1)[0] == JIRA_PATH and method == "POST" and code == 400:
                    ctype = "text/plain; charset=utf-8"
                self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload and method != "HEAD":
                self.wfile.write(payload)

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


def serve(
    home: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    secret: str | None = None,
    allow_ips: set[str] | None = None,
    briefer_nick: str = "",
    filer: intake.GitHubFiler | None = None,
):
    """Blocking listener: public GET digest + gated POST report/git/intake/jira."""
    from http.server import ThreadingHTTPServer

    listen_port = resolve_listen_port(int(port))
    sec = secret if secret is not None else load_secret()
    allow = allow_ips or load_allow_ips()
    use_filer = filer
    if use_filer is None:
        try:
            import gh_filer

            use_filer = gh_filer.default_filer()
        except Exception:
            use_filer = None
    drain_pending(home, secret=sec, briefer_nick=briefer_nick, filer=use_filer)
    handler = make_handler(home, sec, allow, briefer_nick, filer=use_filer)
    httpd = ThreadingHTTPServer((host, listen_port), handler)
    return httpd


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description=(
            "POST /bob/v1/report|/bob/v1/git|/bob/v1/intake|/bob/v1/jira; "
            "GET digest on /bob/v1/report and /bob/v1/digest; GET /bob/v1/jira"
        )
    )
    p.add_argument("--home", default="", help="AGENTIC_IRC_HOME (digest.json)")
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BOB_REPORT_PORT") or str(DEFAULT_PORT)),
        help=f"listen port (0 → BOB_REPORT_PORT or {DEFAULT_PORT}; never ephemeral)",
    )
    args = p.parse_args()
    home = Path(args.home).expanduser() if args.home else bobreport.digest_path(Path(".")).parent
    httpd = serve(home, host=args.bind, port=args.port)
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
