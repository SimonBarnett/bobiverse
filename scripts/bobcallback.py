#!/usr/bin/env python3
"""Digest callback: POST /bob/v1/report + /bob/v1/git; public GET digest (#174).

GET/HEAD on /bob/v1/report returns the JSON digest (same body as /bob/v1/digest).
IIS already proxies reportUrl; browsers must not keep seeing 405.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import bobreport

REPORT_PATH = "/bob/v1/report"
GIT_WEBHOOK_PATH = "/bob/v1/git"
DIGEST_PATH = "/bob/v1/digest"
DIGEST_ALIAS = "/digest"
SECRET_ENV = "BOB_REPORT_SECRET"
ALLOW_ENV = "BOB_REPORT_ALLOW"
# Public read paths (GET/HEAD). REPORT_PATH is also the write URL (POST).
DIGEST_GET_PATHS = frozenset({DIGEST_PATH, DIGEST_ALIAS, REPORT_PATH})


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


def _check_post_route(
    verb: str, route: str, peer_ip: str, allow_ips: set[str] | None
) -> tuple[int, set[str]] | tuple[int, bytes]:
    """Return (0, allow_set) on success, or (http_code, body) on failure."""
    allow = allow_ips if allow_ips is not None else load_allow_ips()
    if route not in (REPORT_PATH, GIT_WEBHOOK_PATH):
        return 404, b""
    if verb != "POST":
        return 405, b""
    ip = (peer_ip or "").split("%", 1)[0]
    if allow and ip not in allow:
        return 403, b""
    return 0, allow


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


def handle_git_webhook(
    headers: dict[str, str],
    body: bytes | str,
    home: Path,
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
            return 400, b""
        return 500, b""
    return 204, b""


def handle_report_post(
    headers: dict[str, str],
    body: bytes | str,
    home: Path,
    secret: str,
    briefer_nick: str = "",
) -> tuple[int, bytes]:
    hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    got = (hdrs.get("x-bob-secret") or "").strip()
    if not secret or got != secret:
        return 401, b""
    payload = _parse_json_body(body)
    if payload is None:
        return 400, b""
    out = bobreport.apply_callback(home, payload, briefer_nick)
    if not out.ok:
        return 400, b""
    if out.body is not None:
        return 200, out.body
    if not out.changed:
        return 200, b""
    return 204, b""


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
    # POST to digest-only aliases is not a write path.
    if route in (DIGEST_PATH, DIGEST_ALIAS):
        return 405, b""
    gate = _check_post_route(verb, route, peer_ip, allow_ips)
    if gate[0] != 0:
        return gate[0], gate[1]
    if route == GIT_WEBHOOK_PATH:
        return handle_git_webhook(headers, body, home)
    return handle_report_post(headers, body, home, secret, briefer_nick)


class ReportHandler:
    """stdlib BaseHTTPRequestHandler mixin state. Instantiated by serve()."""

    home: Path
    secret: str
    allow_ips: set[str]
    briefer_nick: str


def make_handler(home: Path, secret: str, allow_ips: set[str], briefer_nick: str = ""):
    from http.server import BaseHTTPRequestHandler

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
            )
            self.send_response(code)
            if payload:
                self.send_header("Content-Type", "application/json; charset=utf-8")
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
):
    """Blocking listener: public GET digest + gated POST report/git (#174)."""
    from http.server import ThreadingHTTPServer

    handler = make_handler(home, secret if secret is not None else load_secret(), allow_ips or load_allow_ips(), briefer_nick)
    httpd = ThreadingHTTPServer((host, int(port)), handler)
    return httpd


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="POST /bob/v1/report + /bob/v1/git; GET digest on /bob/v1/report and /bob/v1/digest"
    )
    p.add_argument("--home", default="", help="AGENTIC_IRC_HOME (digest.json)")
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("BOB_REPORT_PORT") or "0"))
    args = p.parse_args()
    home = Path(args.home).expanduser() if args.home else bobreport.digest_path(Path(".")).parent
    httpd = serve(home, host=args.bind, port=args.port)
    host, port = httpd.server_address[:2]
    print(
        f"INFO report listen {host}:{port} GET {REPORT_PATH}|{DIGEST_PATH} POST {REPORT_PATH} POST {GIT_WEBHOOK_PATH}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
