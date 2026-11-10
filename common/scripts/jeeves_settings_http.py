"""FR #6440: LAN-bound HTTP listener + schema-driven settings UI for jeeves.ntsa.uk.

Off by default. Enable with ``JEEVES_SETTINGS_HTTP=1`` (or ``JEEVES_SETTINGS_UI=1``).
Binds only to RFC1918 / loopback. Rejects non-LAN peers in ``verify_request``
(socket layer) and again via ``jeeves_settings`` API helpers. Never fronts via
bob.ntsa.uk / irc.ntsa.uk / Cloudflare. Auth is child FR #6441.
"""
from __future__ import annotations

import json
import time
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import jeeves_settings as js

DEFAULT_PORT = 7701
ENV_ENABLE = ("JEEVES_SETTINGS_HTTP", "JEEVES_SETTINGS_UI")
ENV_BIND = "JEEVES_SETTINGS_HTTP_BIND"
ENV_PORT = "JEEVES_SETTINGS_HTTP_PORT"


def settings_http_enabled() -> bool:
    for key in ENV_ENABLE:
        raw = (os.environ.get(key) or "").strip().lower()
        if raw in ("1", "true", "yes", "on"):
            return True
    return False


def validate_bind_host(host: str) -> str | None:
    """Return error when *host* is not a LAN/loopback address we may bind."""
    h = str(host or "").strip()
    if not h:
        return "forbidden: empty bind host"
    if h in ("localhost",):
        return None
    # Hostnames are not allowed for bind (must be an IP we can check).
    if any(c.isalpha() for c in h.replace(".", "").replace(":", "")):
        return "forbidden: bind host must be an IP address"
    if not js.is_rfc1918(h):
        return "forbidden: bind host is not RFC1918/loopback"
    return None


def resolve_bind_host(explicit: str | None = None) -> str:
    raw = (explicit if explicit is not None else os.environ.get(ENV_BIND) or "").strip()
    if not raw:
        return "127.0.0.1"
    err = validate_bind_host(raw)
    if err:
        raise ValueError(err)
    return raw


def resolve_port(explicit: int | None = None) -> int:
    if explicit is not None:
        return int(explicit)
    raw = (os.environ.get(ENV_PORT) or "").strip()
    if raw:
        return int(raw)
    return int(DEFAULT_PORT)


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    try:
        return str(handler.client_address[0] or "")
    except Exception:
        return ""


def _json_bytes(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def _render_html(settings: list[dict[str, Any]]) -> str:
    rows = []
    for s in settings:
        key = s.get("key") or ""
        typ = s.get("type") or "str"
        val = s.get("value") or ""
        src = s.get("source") or ""
        secret = bool(s.get("secret"))
        restart = " yes" if s.get("restart") else ""
        desc = (s.get("description") or "").replace("<", "&lt;")
        if secret:
            inp = (
                f'<input name="{key}" type="password" placeholder="{val}" '
                f'autocomplete="off" data-secret="1"/>'
            )
        else:
            safe = str(val).replace('"', "&quot;")
            inp = f'<input name="{key}" type="text" value="{safe}"/>'
        rows.append(
            f"<tr><td><code>{key}</code></td><td>{typ}</td><td>{inp}</td>"
            f"<td>{src}</td><td>{restart}</td><td>{desc}</td></tr>"
        )
    body = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Jeeves appliance settings</title>
<style>
body{{font-family:system-ui,sans-serif;margin:1.5rem;}}
table{{border-collapse:collapse;width:100%;}}
th,td{{border:1px solid #ccc;padding:.4rem;text-align:left;vertical-align:top;}}
th{{background:#f4f4f4;}}
code{{font-size:.9em;}}
.note{{color:#444;margin-bottom:1rem;}}
button{{margin-top:1rem;padding:.4rem .8rem;}}
</style></head><body>
<h1>Jeeves appliance settings</h1>
<p class="note">LAN-only (FR #6440). Secrets are write-only (set/unset).
Auth lands in FR #6441. Never expose via bob.ntsa.uk. <a href="/status">Status</a></p>
<table>
<thead><tr><th>Key</th><th>Type</th><th>Value</th><th>Source</th><th>Restart</th><th>Description</th></tr></thead>
<tbody>
{body}
</tbody></table>
<p><button type="button" id="save">Save changed fields</button>
<span id="status"></span></p>
<script>
async function save() {{
  const status = document.getElementById('status');
  status.textContent = 'saving…';
  const inputs = document.querySelectorAll('input[name]');
  let ok = 0, fail = 0;
  for (const el of inputs) {{
    const key = el.name;
    let value = el.value;
    if (el.dataset.secret === '1' && !value) continue;
    const r = await fetch('/api/settings/' + encodeURIComponent(key), {{
      method: 'PUT',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{value, actor: 'ui'}})
    }});
    const j = await r.json().catch(() => ({{}}));
    if (j.ok) ok++; else fail++;
  }}
  status.textContent = 'saved=' + ok + ' failed=' + fail;
  if (fail === 0) location.reload();
}}
document.getElementById('save').onclick = save;
</script>
</body></html>
"""


def _render_status_html(status: dict[str, Any]) -> str:
    q = status.get("queue") if isinstance(status.get("queue"), dict) else {}
    seats = status.get("seats") if isinstance(status.get("seats"), dict) else {}
    fuel = status.get("fuel") if isinstance(status.get("fuel"), dict) else {}
    pending = "yes" if status.get("restart_pending") else "no"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Jeeves status</title>
<style>body{{font-family:system-ui,sans-serif;margin:1.5rem;}} code{{font-size:.9em;}}</style>
</head><body>
<h1>Jeeves status</h1>
<p class="note">Read-only (FR #6443). No secrets. <a href="/">Settings</a></p>
<ul>
<li>version: <code>{status.get("version") or ""}</code></li>
<li>source_commit: <code>{status.get("source_commit") or ""}</code></li>
<li>uptime_s: <code>{status.get("uptime_s")}</code></li>
<li>queue: unaccepted=<code>{q.get("unaccepted")}</code> accepted=<code>{q.get("accepted")}</code></li>
<li>seats: live=<code>{seats.get("live_n")}</code> idle=<code>{seats.get("idle_n")}</code></li>
<li>fuel active: <code>{", ".join(fuel.get("active") or []) or "(none)"}</code></li>
<li>restart_pending: <code>{pending}</code></li>
</ul>
<p><button type="button" id="restart">Restart ircJeeves when idle</button>
<span id="rstatus"></span></p>
<script>
document.getElementById('restart').onclick = async () => {{
  const el = document.getElementById('rstatus');
  el.textContent = 'requesting…';
  const r = await fetch('/api/restart-when-idle', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{actor: 'ui'}})
  }});
  const j = await r.json().catch(() => ({{}}));
  el.textContent = JSON.stringify(j);
}};
</script>
</body></html>
"""


class SettingsHTTPServer(ThreadingHTTPServer):
    """Threading server that refuses non-LAN peers before handle_request."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address,
        RequestHandlerClass,
        *,
        home: Path,
        digest_home: Path | None = None,
        started: float | None = None,
    ):
        self.home = Path(home)
        self.digest_home = Path(digest_home) if digest_home is not None else Path(home)
        self.started = float(started if started is not None else time.time())
        super().__init__(server_address, RequestHandlerClass)

    def verify_request(self, request, client_address) -> bool:  # noqa: ANN001
        try:
            ip = str(client_address[0] if client_address else "")
        except Exception:
            return False
        return js.reject_non_lan(ip) is None


class _Handler(BaseHTTPRequestHandler):
    server: SettingsHTTPServer  # type: ignore[assignment]

    def log_message(self, fmt: str, *args: Any) -> None:
        # Never log request bodies (may contain secrets). Short access line only.
        try:
            msg = fmt % args
        except Exception:
            msg = fmt
        if any(x in msg.lower() for x in ("token", "password", "secret", "bearer")):
            msg = "[redacted]"
        # Intentionally quiet in tests; chair can wrap via maybe_start log.

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, doc: dict[str, Any]) -> None:
        self._send(code, _json_bytes(doc), "application/json; charset=utf-8")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            doc = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        ip = _client_ip(self)
        path = urlparse(self.path).path
        home = self.server.home
        if path in ("/", "/index.html", "/ui"):
            view = js.api_get_settings(home, client_ip=ip)
            if not view.get("ok"):
                self._send_json(403, view)
                return
            html = _render_html(list(view.get("settings") or []))
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/settings":
            view = js.api_get_settings(home, client_ip=ip)
            code = 200 if view.get("ok") else 403
            self._send_json(code, view)
            return
        if path == "/api/schema":
            err = js.reject_non_lan(ip)
            if err:
                self._send_json(403, {"ok": False, "error": err})
                return
            rows = [
                {
                    "key": s.key,
                    "type": s.type,
                    "default": "" if s.secret else s.default,
                    "store": s.store,
                    "restart": s.restart,
                    "secret": s.secret,
                    "description": s.description,
                }
                for s in js.SCHEMA
            ]
            self._send_json(200, {"ok": True, "schema": rows})
            return
        if path in ("/status", "/ui/status"):
            view = js.api_get_status(
                home,
                client_ip=ip,
                digest_home=self.server.digest_home,
                started=self.server.started,
            )
            if not view.get("ok"):
                self._send_json(403, view)
                return
            html = _render_status_html(view)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            view = js.api_get_status(
                home,
                client_ip=ip,
                digest_home=self.server.digest_home,
                started=self.server.started,
            )
            code = 200 if view.get("ok") else 403
            self._send_json(code, view)
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_PUT(self) -> None:  # noqa: N802
        ip = _client_ip(self)
        path = urlparse(self.path).path
        prefix = "/api/settings/"
        if not path.startswith(prefix):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        key = unquote(path[len(prefix) :]).strip()
        doc = self._read_json()
        result = js.api_put_setting(
            self.server.home,
            client_ip=ip,
            key=key,
            value=doc.get("value"),
            actor=str(doc.get("actor") or "http")[:80],
        )
        code = 200 if result.get("ok") else (403 if "forbidden" in str(result.get("error") or "") else 400)
        self._send_json(code, result)

    def do_POST(self) -> None:  # noqa: N802
        ip = _client_ip(self)
        path = urlparse(self.path).path
        doc = self._read_json()
        if path == "/api/rollback":
            result = js.api_rollback(
                self.server.home,
                client_ip=ip,
                backup_id=str(doc.get("backup_id") or ""),
                actor=str(doc.get("actor") or "http")[:80],
            )
            code = 200 if result.get("ok") else (403 if "forbidden" in str(result.get("error") or "") else 400)
            self._send_json(code, result)
            return
        if path == "/api/restart-when-idle":
            result = js.request_restart_when_idle(
                self.server.home,
                client_ip=ip,
                digest_home=self.server.digest_home,
                actor=str(doc.get("actor") or "http")[:80],
            )
            code = 200 if result.get("ok") else (403 if "forbidden" in str(result.get("error") or "") else 400)
            self._send_json(code, result)
            return
        self._send_json(404, {"ok": False, "error": "not found"})


def start_settings_http(
    home: Path,
    *,
    bind: str | None = None,
    port: int | None = None,
    digest_home: Path | None = None,
    started: float | None = None,
) -> SettingsHTTPServer | None:
    """Start the LAN settings listener when enabled. None when off or bind refused."""
    if not settings_http_enabled():
        return None
    try:
        host = resolve_bind_host(bind)
        p = resolve_port(port)
    except (ValueError, TypeError):
        return None
    err = validate_bind_host(host)
    if err:
        return None
    try:
        srv = SettingsHTTPServer(
            (host, p),
            _Handler,
            home=Path(home),
            digest_home=Path(digest_home) if digest_home is not None else Path(home),
            started=started,
        )
    except OSError:
        return None
    t = threading.Thread(target=srv.serve_forever, name="jeeves-settings-http", daemon=True)
    t.start()
    srv._bob_thread = t  # type: ignore[attr-defined]
    return srv


def stop_settings_http(srv: SettingsHTTPServer | None) -> None:
    if srv is None:
        return
    with __import__("contextlib").suppress(Exception):
        srv.shutdown()
    with __import__("contextlib").suppress(Exception):
        srv.server_close()


def maybe_start_from_chair(
    home: Path,
    *,
    log: Callable[[str], None] | None = None,
    digest_home: Path | None = None,
    started: float | None = None,
) -> SettingsHTTPServer | None:
    """Chair hook: start when enabled; log one line; never raise."""
    try:
        if not settings_http_enabled():
            return None
        srv = start_settings_http(
            home, digest_home=digest_home, started=started
        )
        if log:
            if srv is None:
                log("WARN settings-http enabled but failed to bind (check LAN bind/port)")
            else:
                host, port = srv.server_address[:2]
                log(f"INFO settings-http listening on {host}:{port} (FR #6440)")
        return srv
    except Exception as e:  # noqa: BLE001
        if log:
            log(f"WARN settings-http start failed: {type(e).__name__}")
        return None
