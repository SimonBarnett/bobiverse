# -*- coding: utf-8 -*-
"""FR #9273: BobModelsWebhook IIS rule must forward PUT (Weights Save)."""
from __future__ import annotations

import re
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
DOCS = REPO / "jeeves" / "docs" / "webhooks.md"
MODELS_HTML = REPO / "jeeves" / "www" / "irc-ntsa" / "docs" / "webhooks" / "models.html"
WEBHOOK_DOCS = REPO / "common" / "scripts" / "bob_webhook_docs.py"
PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")

# Grouped pattern — FR #9273 (old ^GET|HEAD|POST$ was ungrouped and omitted PUT).
MODELS_METHODS_PATTERN = r"^(GET|HEAD|POST|PUT)$"
MODELS_METHODS = frozenset({"GET", "HEAD", "POST", "PUT"})


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _models_method_patterns(text: str) -> list[str]:
    """Return REQUEST_METHOD patterns inside every BobModelsWebhook rule block."""
    out: list[str] = []
    for m in re.finditer(
        r'<rule\s+name="BobModelsWebhook"[^>]*>.*?</rule>',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        block = m.group(0)
        for pm in re.finditer(
            r'input="\{REQUEST_METHOD\}"\s+pattern="([^"]+)"',
            block,
            flags=re.IGNORECASE,
        ):
            out.append(pm.group(1))
    return out


def test_fr9273_install_script_pins_grouped_put_pattern():
    text = SCRIPT.read_text(encoding="utf-8")
    assert not SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf")
    # Both template and Set-BobOwnedRewriteRule repair path.
    assert text.count(f'pattern="{MODELS_METHODS_PATTERN}"') >= 2
    assert 'pattern="^GET|HEAD|POST$"' not in text
    assert "FR #9273" in text
    pats = _models_method_patterns(text)
    assert len(pats) >= 2
    for pat in pats:
        assert pat == MODELS_METHODS_PATTERN
        rx = re.compile(pat)
        for verb in MODELS_METHODS:
            assert rx.match(verb), f"{pat} must match {verb}"
        assert not rx.match("PATCH")
        assert not rx.match("DELETE")


def test_fr9273_backend_routes_covered_by_iis_method_filters():
    """Every bobcallback write/read verb for models must pass BobModelsWebhook."""
    import sys

    scripts = str(REPO / "common" / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import bobcallback as bc

    text = SCRIPT.read_text(encoding="utf-8")
    pats = _models_method_patterns(text)
    assert pats, "BobModelsWebhook must declare a REQUEST_METHOD condition"
    # All copies must agree.
    assert len(set(pats)) == 1
    rx = re.compile(pats[0])

    # Route inventory the models rule must admit.
    required = {
        ("PUT", bc.MODELS_PATH),
        ("GET", bc.MODELS_PATH),
        ("HEAD", bc.MODELS_PATH),
        ("POST", bc.MODELS_REFRESH_PATH),
    }
    for verb, route in required:
        assert route.startswith("/bob/v1/models"), route
        assert verb in bc.PUT_ROUTES or verb in ("GET", "HEAD") or (
            verb == "POST" and route in bc.POST_ROUTES
        ) or (verb == "PUT" and route in bc.PUT_ROUTES)
        assert rx.match(verb), f"IIS BobModelsWebhook must forward {verb} for {route}"

    # Sanity: PUT is in PUT_ROUTES so a new verb without rule update fails this test.
    assert bc.MODELS_PATH in bc.PUT_ROUTES
    assert bc.MODELS_REFRESH_PATH in bc.POST_ROUTES


def test_fr9273_docs_state_iis_forwards_put():
    md = DOCS.read_text(encoding="utf-8")
    assert "PUT" in md and "BobModelsWebhook" in md
    assert re.search(r"GET\|HEAD\|POST\|PUT|GET, HEAD, POST, and PUT|forwards GET\|HEAD\|POST\|PUT", md)
    html = MODELS_HTML.read_text(encoding="utf-8")
    assert "PUT" in html
    assert "GET" in html and "HEAD" in html and "POST" in html
    # Must not still claim PUT is blocked / coming-only for IIS.
    docs_py = WEBHOOK_DOCS.read_text(encoding="utf-8")
    assert "FR #9273" in docs_py or "GET|HEAD|POST|PUT" in docs_py or "forwards PUT" in docs_py.lower()


class _PutOkHandler(BaseHTTPRequestHandler):
    """Backend stand-in: GET report 200; PUT models 403 JSON (peer gate class)."""

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/bob/v1/report":
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_PUT(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if self.path.rstrip("/") == "/bob/v1/models":
            body = b'{"error":"peer_denied"}'
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


def _run(site: Path, *extra: str, backend: str) -> subprocess.CompletedProcess[str]:
    assert PS
    args = [
        PS,
        "-NoProfile",
        "-File",
        str(SCRIPT),
        "-PhysicalPath",
        str(site),
        "-Backend",
        backend,
        *extra,
    ]
    return subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)


@NEED_PS
def test_fr9273_generated_webconfig_allows_put(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    r = _run(site, "-SkipBackendProbe", backend="http://127.0.0.1:1")
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    cfg = (site / "web.config").read_text(encoding="utf-8")
    pats = _models_method_patterns(cfg)
    assert pats and all(p == MODELS_METHODS_PATTERN for p in pats)
    rx = re.compile(pats[0])
    assert rx.match("PUT")


@NEED_PS
def test_fr9273_post_install_put_probe_reaches_backend(tmp_path: Path):
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _PutOkHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        site = tmp_path / "irc-ntsa"
        site.mkdir()
        backend = f"http://127.0.0.1:{port}"
        r = _run(site, backend=backend)
        out = (r.stdout or "") + (r.stderr or "")
        assert r.returncode == 0, out
        assert "FR #9246 backend probe OK" in out or "backend probe OK" in out
        assert "FR #9273" in out and "PUT" in out
        assert "models put probe OK" in out.lower() or "PUT probe OK" in out
        assert "IIS HTML 404" not in out
    finally:
        httpd.shutdown()
        httpd.server_close()
