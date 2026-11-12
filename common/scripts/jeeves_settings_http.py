"""FR #6440 / #6451: LAN-bound HTTP listener + schema UI with session auth.

Off by default. Enable with ``JEEVES_SETTINGS_HTTP=1`` (or ``JEEVES_SETTINGS_UI=1``).
Binds only to RFC1918 / loopback. Rejects non-LAN peers in ``verify_request``
(socket layer). Settings/status mutating routes require FR #6441 sessions
(cookie ``jeeves_appliance_session`` or ``Authorization: Bearer``). Never fronts
via bob.ntsa.uk / irc.ntsa.uk / Cloudflare.
"""
from __future__ import annotations

import html
import json
import time
import os
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import jeeves_settings as js
import jeeves_settings_auth as auth

DEFAULT_PORT = 7701
ENV_ENABLE = ("JEEVES_SETTINGS_HTTP", "JEEVES_SETTINGS_UI")
ENV_BIND = "JEEVES_SETTINGS_HTTP_BIND"
ENV_PORT = "JEEVES_SETTINGS_HTTP_PORT"
ENV_FRONTDOOR = "JEEVES_SETTINGS_FRONTDOOR"
SESSION_COOKIE_NAME = "jeeves_appliance_session"
LOGO_HREF = "/assets/ntsa-gut-logo.png"
_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_TRAY_LOGO = _REPO_ROOT / "bob" / "tray" / "assets" / "ntsa-gut-logo.png"
_PACK_LOGO = (
    _REPO_ROOT
    / "jeeves"
    / "docs"
    / "appliance-ui-20261112"
    / "mocks"
    / "ntsa-gut-logo.png"
)


def ntsa_gut_logo_path() -> Path:
    """Git logo bytes: tray asset, else the docs pack copy (same file, no new art)."""
    if _TRAY_LOGO.is_file():
        return _TRAY_LOGO
    return _PACK_LOGO


def _shell_header(*, current: str, include_nav: bool) -> str:
    img = f'<img src="{LOGO_HREF}" alt="NTSA"/>'
    if not include_nav:
        return f"<header>{img}<strong>Jeeves</strong></header>"
    links = [
        ("/", "Settings", "settings"),
        ("/queue", "Queue", "queue"),
        ("/status", "Status", "status"),
        ("/logout", "Log out", "logout"),
    ]
    parts = []
    for href, label, key in links:
        cur = ' aria-current="page"' if current == key else ""
        parts.append(f'<a href="{href}"{cur}>{label}</a>')
    nav = "<nav>" + " · ".join(parts) + "</nav>"
    return f"<header>{img}<strong>Jeeves</strong>{nav}</header>"


def _shell_css() -> str:
    return (
        "header{display:flex;align-items:center;gap:1rem;margin-bottom:1rem;}"
        "header img{height:36px;width:36px;}"
        "nav{margin-left:auto;}"
    )


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


def front_door_enabled() -> bool:
    raw = (os.environ.get(ENV_FRONTDOOR) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def resolve_bind_host(explicit: str | None = None) -> str:
    if front_door_enabled():
        return "127.0.0.1"
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
        peer = str(handler.client_address[0] or "")
    except Exception:
        peer = ""
    xff = handler.headers.get("X-Forwarded-For") if getattr(handler, "headers", None) else None
    return js.effective_client_ip(peer, xff)


def _json_bytes(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def _truthy_setting(raw: Any) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _opt_esc(raw: Any) -> str:
    return (
        str(raw)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace('"', "&quot;")
    )


def render_setting_input(s: dict[str, Any]) -> str:
    """HTML control: bool checkbox (FR #6750); non-empty choices => select (FR #6753)."""
    key = str(s.get("key") or "")
    typ = str(s.get("type") or "str")
    val = "" if s.get("value") is None else str(s.get("value"))
    secret = bool(s.get("secret")) or typ == "secret"
    if secret:
        return (
            f'<input name="{key}" type="password" placeholder="{_opt_esc(val)}" '
            f'autocomplete="off" data-secret="1"/>'
        )
    if typ == "bool":
        checked = " checked" if _truthy_setting(val) else ""
        return f'<input name="{key}" type="checkbox" value="1"{checked}/>'
    raw_choices = s.get("choices") or ()
    choices = [str(c) for c in raw_choices if str(c) != ""]
    if choices:
        cur = val
        opts = list(choices)
        # Empty current value is outside the list too (FR #6753); keep it selected.
        if cur not in opts:
            opts.append(cur)
        parts = []
        for c in opts:
            sel = " selected" if c == cur else ""
            parts.append(f'<option value="{_opt_esc(c)}"{sel}>{_opt_esc(c)}</option>')
        return f'<select name="{key}">{"".join(parts)}</select>'
    safe = _opt_esc(val)
    return f'<input name="{key}" type="text" value="{safe}"/>'


def collect_save_puts(controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror of the settings page save() loop (FR #6750).

    Checkbox posts 1 when checked and 0 when not. Blank secrets are skipped.
    """
    puts: list[dict[str, Any]] = []
    for el in controls:
        key = str(el.get("name") or "")
        if not key:
            continue
        kind = str(el.get("type") or "text").lower()
        secret = bool(el.get("secret")) or str(el.get("datasetSecret") or "") == "1"
        if kind == "checkbox":
            value = "1" if el.get("checked") else "0"
        else:
            value = "" if el.get("value") is None else str(el.get("value"))
        if secret and not value:
            continue
        puts.append({"key": key, "body": {"value": value}})
    return puts


def _render_html(settings: list[dict[str, Any]]) -> str:
    rows = []
    for s in settings:
        key = s.get("key") or ""
        typ = s.get("type") or "str"
        src = s.get("source") or ""
        restart = " yes" if s.get("restart") else ""
        desc = (s.get("description") or "").replace("<", "&lt;")
        secret = bool(s.get("secret"))
        # FR #6751 / FR-03: show schema default next to the control. Secrets
        # always render an empty default (never invent or echo a secret).
        raw_default = "" if secret else str(s.get("default") or "")
        safe_default_attr = (
            raw_default.replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
        )
        default_text = (
            raw_default.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        default_cell = (
            f'<td class="setting-default" data-default="{safe_default_attr}">'
            f"{default_text}</td>"
        )
        inp = render_setting_input(s)
        rows.append(
            f"<tr><td><code>{key}</code></td><td>{typ}</td><td>{inp}</td>"
            f"{default_cell}<td>{src}</td><td>{restart}</td><td>{desc}</td></tr>"
        )
    body = "\n".join(rows)
    header = _shell_header(current="settings", include_nav=True)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Jeeves appliance settings</title>
<style>
body{{font-family:system-ui,sans-serif;margin:1.5rem;}}
{_shell_css()}
table{{border-collapse:collapse;width:100%;}}
th,td{{border:1px solid #ccc;padding:.4rem;text-align:left;vertical-align:top;}}
th{{background:#f4f4f4;}}
code{{font-size:.9em;}}
.setting-default{{color:#555;font-family:ui-monospace,monospace;font-size:.9em;}}
.note{{color:#444;margin-bottom:1rem;}}
button{{margin-top:1rem;padding:.4rem .8rem;}}
</style></head><body>
{header}
<h1>Jeeves appliance settings</h1>
<p class="note">LAN-only (FR #6440 / #6451). Secrets are write-only (set/unset).
Session cookie required. Never expose via bob.ntsa.uk.
Defaults (FR #6751) are shown for non-secret keys; the Value control keeps the current value.</p>
<table>
<thead><tr><th>Key</th><th>Type</th><th>Value</th><th>Default</th><th>Source</th><th>Restart</th><th>Description</th></tr></thead>
<tbody>
{body}
</tbody></table>
<p><button type="button" id="save">Save changed fields</button>
<span id="status"></span></p>
<script>
async function save() {{
  const status = document.getElementById('status');
  status.textContent = 'saving…';
  const inputs = document.querySelectorAll('input[name], select[name]');
  let ok = 0, fail = 0;
  for (const el of inputs) {{
    const key = el.name;
    let value = el.value;
    if (el.type === 'checkbox') value = el.checked ? '1' : '0';
    if (el.dataset.secret === '1' && !value) continue;
    const r = await fetch('/api/settings/' + encodeURIComponent(key), {{
      method: 'PUT',
      credentials: 'same-origin',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{value}})
    }});
    if (r.status === 401 || r.status === 403) {{ location.href = '/login'; return; }}
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


def _render_login_html(error: str = "") -> str:
    err = (error or "").replace("<", "&lt;")
    note = f'<p class="note" style="color:#a00">{err}</p>' if err else ""
    header = _shell_header(current="login", include_nav=False)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Jeeves settings login</title>
<style>
body{{font-family:system-ui,sans-serif;margin:1.5rem;max-width:28rem;}}
{_shell_css()}
label{{display:block;margin:.6rem 0 .2rem;}}
input{{width:100%;padding:.4rem;box-sizing:border-box;}}
button{{margin-top:1rem;padding:.4rem .8rem;}}
.note{{color:#444;}}
</style></head><body>
{header}
<h1>Jeeves settings login</h1>
<p class="note">LAN-only AD/Windows or CredMan (FR #6441 / #6451). Passwords are never logged.</p>
{note}
<form id="f">
<label>User name<input name="account" autocomplete="username" required placeholder="DOMAIN\\user or user@domain"/></label>
<label>Password<input name="password" type="password" autocomplete="current-password" required/></label>
<button type="submit">Sign in</button>
<span id="status"></span>
</form>
<script>
document.getElementById('f').onsubmit = async (ev) => {{
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const status = document.getElementById('status');
  status.textContent = '…';
  const r = await fetch('/api/login', {{
    method: 'POST',
    credentials: 'same-origin',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{
      username: fd.get('account') || '',
      password: fd.get('password') || ''
    }})
  }});
  const j = await r.json().catch(() => ({{}}));
  if (j.ok) {{ location.href = '/'; return; }}
  status.textContent = j.error || ('HTTP ' + r.status);
}};
</script>
</body></html>
"""


def _queue_row_public(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("repo", "task", "id"):
        val = row.get(key)
        if val is None or str(val).strip() == "":
            continue
        out[key] = val
    worker = row.get("worker")
    if worker is None or str(worker).strip() == "":
        worker = row.get("nick")
    if worker is not None and str(worker).strip() != "":
        out["worker"] = str(worker)
    return out


def _load_queue_public_lists(digest_home: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unaccepted: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    try:
        import gitclaim

        path = gitclaim.queue_path(Path(digest_home))
        raw: dict[str, Any] = {}
        if path.is_file():
            parsed = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(parsed, dict):
                raw = parsed
        unaccepted = [_queue_row_public(r) for r in (raw.get("unaccepted") or [])]
        accepted = [_queue_row_public(r) for r in (raw.get("accepted") or [])]
    except Exception:
        pass
    return unaccepted, accepted


def _render_queue_list(rows: list[dict[str, Any]], empty_copy: str) -> str:
    if not rows:
        return f'<p class="empty">{html.escape(empty_copy)}</p>'
    items = []
    for row in rows:
        bits = [html.escape(str(row[k])) for k in ("repo", "task", "id") if k in row]
        line = " ".join(bits)
        if row.get("worker"):
            line = f"{line} · {html.escape(str(row['worker']))}"
        items.append(f"<li>{line}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def _render_queue_html(
    unaccepted: list[dict[str, Any]], accepted: list[dict[str, Any]]
) -> str:
    waiting = _render_queue_list(unaccepted, "Nothing is waiting.")
    progress = _render_queue_list(accepted, "Nothing is in progress.")
    header = _shell_header(current="queue", include_nav=True)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Jeeves queue</title>
<style>
body{{font-family:system-ui,sans-serif;margin:1.5rem;}}
{_shell_css()}
section{{margin-bottom:1.2rem;}}
.empty{{color:#444;}}
</style></head><body>
{header}
<h1>Queue</h1>
<section>
<h2>Waiting</h2>
{waiting}
</section>
<section>
<h2>In progress</h2>
{progress}
</section>
</body></html>
"""


def _render_status_html(status: dict[str, Any]) -> str:
    q = status.get("queue") if isinstance(status.get("queue"), dict) else {}
    seats = status.get("seats") if isinstance(status.get("seats"), dict) else {}
    fuel = status.get("fuel") if isinstance(status.get("fuel"), dict) else {}
    pending = "yes" if status.get("restart_pending") else "no"
    header = _shell_header(current="status", include_nav=True)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Jeeves status</title>
<style>body{{font-family:system-ui,sans-serif;margin:1.5rem;}} {_shell_css()} code{{font-size:.9em;}}</style>
</head><body>
{header}
<h1>Jeeves status</h1>
<p class="note">Read-only (FR #6443). No secrets.</p>
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
    credentials: 'same-origin',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{}})
  }});
  if (r.status === 401 || r.status === 403) {{ location.href = '/login'; return; }}
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
        authenticator: Callable[..., bool] | None = None,
    ):
        self.home = Path(home)
        self.digest_home = Path(digest_home) if digest_home is not None else Path(home)
        self.started = float(started if started is not None else time.time())
        self.authenticator = authenticator
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

    def _send(
        self,
        code: int,
        body: bytes,
        content_type: str,
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra_headers or ():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self,
        code: int,
        doc: dict[str, Any],
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self._send(
            code,
            _json_bytes(doc),
            "application/json; charset=utf-8",
            extra_headers=extra_headers,
        )

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            doc = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def _session_token(self) -> str | None:
        authz = (self.headers.get("Authorization") or "").strip()
        if authz.lower().startswith("bearer "):
            tok = authz[7:].strip()
            return tok or None
        raw = self.headers.get("Cookie") or ""
        if not raw:
            return None
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except Exception:
            return None
        morsel = jar.get(SESSION_COOKIE_NAME)
        if morsel is None:
            return None
        tok = str(morsel.value or "").strip()
        return tok or None

    def _auth_code(self, result: dict[str, Any]) -> int:
        err = str(result.get("error") or "")
        if err.startswith("unauthorized"):
            return 401
        if "forbidden" in err:
            return 403
        return 400

    def _session_cookie_header(self, token: str, *, max_age: int) -> str:
        # LAN HTTP may be plain http://; omit Secure. HttpOnly + SameSite=Strict.
        return (
            f"{SESSION_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; "
            f"Max-Age={int(max_age)}"
        )

    def _clear_session_cookie_header(self) -> str:
        return f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"

    def _refuse_non_lan(self, ip: str) -> bool:
        err = js.reject_non_lan(ip)
        if err:
            self._send_json(403, {"ok": False, "error": err})
            return True
        return False

    def do_GET(self) -> None:  # noqa: N802
        ip = _client_ip(self)
        if self._refuse_non_lan(ip):
            return
        path = urlparse(self.path).path
        home = self.server.home
        tok = self._session_token()
        if path == LOGO_HREF:
            logo = ntsa_gut_logo_path()
            if not logo.is_file():
                self._send_json(404, {"ok": False, "error": "not found"})
                return
            self._send(200, logo.read_bytes(), "image/png")
            return
        if path in ("/login", "/ui/login"):
            html = _render_login_html()
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path in ("/logout", "/ui/logout"):
            auth.logout(home, client_ip=ip, session_token=tok)
            html = _render_login_html("Signed out.")
            self._send(
                200,
                html.encode("utf-8"),
                "text/html; charset=utf-8",
                extra_headers=[("Set-Cookie", self._clear_session_cookie_header())],
            )
            return
        if path in ("/", "/index.html", "/ui"):
            view = auth.api_get_settings_authed(
                home, client_ip=ip, session_token=tok
            )
            if not view.get("ok"):
                html = _render_login_html(str(view.get("error") or "Sign in required"))
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                return
            html = _render_html(list(view.get("settings") or []))
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/settings":
            view = auth.api_get_settings_authed(
                home, client_ip=ip, session_token=tok
            )
            code = 200 if view.get("ok") else self._auth_code(view)
            self._send_json(code, view)
            return
        if path == "/api/schema":
            # Schema is non-secret metadata but still session-gated on the LAN UI.
            gate = auth.require_session(
                home, client_ip=ip, session_token=tok
            )
            if not gate.get("ok"):
                self._send_json(self._auth_code(gate), gate)
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
            gate = auth.require_session(
                home, client_ip=ip, session_token=tok
            )
            if not gate.get("ok"):
                html = _render_login_html(str(gate.get("error") or "Sign in required"))
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                return
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
        if path in ("/queue", "/ui/queue"):
            gate = auth.require_session(
                home, client_ip=ip, session_token=tok
            )
            if not gate.get("ok"):
                html = _render_login_html(str(gate.get("error") or "Sign in required"))
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                return
            err = js.reject_non_lan(ip)
            if err:
                self._send_json(403, {"ok": False, "error": err})
                return
            unaccepted, accepted = _load_queue_public_lists(
                self.server.digest_home
            )
            html = _render_queue_html(unaccepted, accepted)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            gate = auth.require_session(
                home, client_ip=ip, session_token=tok
            )
            if not gate.get("ok"):
                self._send_json(self._auth_code(gate), gate)
                return
            view = js.api_get_status(
                home,
                client_ip=ip,
                digest_home=self.server.digest_home,
                started=self.server.started,
            )
            code = 200 if view.get("ok") else 403
            self._send_json(code, view)
            return
        if path == "/api/queue":
            gate = auth.require_session(
                home, client_ip=ip, session_token=tok
            )
            if not gate.get("ok"):
                self._send_json(self._auth_code(gate), gate)
                return
            view = js.api_get_queue(
                home,
                client_ip=ip,
                digest_home=self.server.digest_home,
            )
            code = 200 if view.get("ok") else 403
            self._send_json(code, view)
            return
        if path == "/api/pools":
            gate = auth.require_session(
                home, client_ip=ip, session_token=tok
            )
            if not gate.get("ok"):
                self._send_json(self._auth_code(gate), gate)
                return
            view = js.api_get_pools(
                home,
                client_ip=ip,
                digest_home=self.server.digest_home,
            )
            code = 200 if view.get("ok") else 403
            self._send_json(code, view)
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_PUT(self) -> None:  # noqa: N802
        ip = _client_ip(self)
        if self._refuse_non_lan(ip):
            return
        path = urlparse(self.path).path
        prefix = "/api/settings/"
        if not path.startswith(prefix):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        key = unquote(path[len(prefix) :]).strip()
        doc = self._read_json()
        result = auth.api_put_setting_authed(
            self.server.home,
            client_ip=ip,
            session_token=self._session_token(),
            key=key,
            value=doc.get("value"),
        )
        code = 200 if result.get("ok") else self._auth_code(result)
        self._send_json(code, result)

    def do_POST(self) -> None:  # noqa: N802
        ip = _client_ip(self)
        if self._refuse_non_lan(ip):
            return
        path = urlparse(self.path).path
        doc = self._read_json()
        if path == "/api/login":
            # Never echo password fields back.
            result = auth.login(
                self.server.home,
                client_ip=ip,
                username=str(doc.get("username") or doc.get("account") or ""),
                password=str(doc.get("password") or ""),
                domain=str(doc.get("domain") or ""),
                authenticator=self.server.authenticator,
            )
            if result.get("ok"):
                tok = str(result.get("session_token") or "")
                max_age = int(result.get("expires_in") or auth.SESSION_TTL_S)
                # Response body still includes session_token for bearer clients;
                # cookie is for browsers. Password keys are never present.
                safe = {
                    k: v
                    for k, v in result.items()
                    if k not in ("password", "passwd", "secret")
                }
                self._send_json(
                    200,
                    safe,
                    extra_headers=[
                        ("Set-Cookie", self._session_cookie_header(tok, max_age=max_age))
                    ],
                )
                return
            self._send_json(self._auth_code(result), result)
            return
        if path == "/api/logout":
            result = auth.logout(
                self.server.home,
                client_ip=ip,
                session_token=self._session_token(),
            )
            self._send_json(
                200 if result.get("ok") else self._auth_code(result),
                result,
                extra_headers=[("Set-Cookie", self._clear_session_cookie_header())],
            )
            return
        if path == "/api/rollback":
            result = auth.api_rollback_authed(
                self.server.home,
                client_ip=ip,
                session_token=self._session_token(),
                backup_id=str(doc.get("backup_id") or ""),
            )
            code = 200 if result.get("ok") else self._auth_code(result)
            self._send_json(code, result)
            return
        if path == "/api/restart-when-idle":
            gate = auth.require_session(
                self.server.home,
                client_ip=ip,
                session_token=self._session_token(),
            )
            if not gate.get("ok"):
                self._send_json(self._auth_code(gate), gate)
                return
            result = js.request_restart_when_idle(
                self.server.home,
                client_ip=ip,
                digest_home=self.server.digest_home,
                actor=str(gate.get("actor") or "http")[:80],
            )
            code = 200 if result.get("ok") else (
                403 if "forbidden" in str(result.get("error") or "") else 400
            )
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
    authenticator: Callable[..., bool] | None = None,
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
            authenticator=authenticator,
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
