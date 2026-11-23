"""FR #9246: Install-BobWebhooks post-install backend probe (WARN / Require / Skip)."""
from __future__ import annotations

import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _ReportHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/bob/v1/report":
            body = b'{"ok":true,"fr":9246}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


def _run(site: Path, *extra: str, backend: str = "http://127.0.0.1:1") -> subprocess.CompletedProcess[str]:
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


def test_fr9246_script_pins_probe_switches_ascii():
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "Install-BobWebhooks.ps1 must be BOM-less"
    text = raw.decode("ascii")
    assert "SkipBackendProbe" in text
    assert "RequireBackend" in text
    assert "FR #9246" in text
    assert "/bob/v1/report" in text
    assert "TcpClient" in text


@NEED_PS
def test_fr9246_skip_probe_no_warn_on_dead_backend(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    r = _run(site, "-SkipBackendProbe", backend="http://127.0.0.1:1")
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "backend probe" not in out.lower()
    assert "INFO Install-BobWebhooks done" in out


@NEED_PS
def test_fr9246_default_warns_when_backend_down(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    # Port 1 is almost never listening; TCP wait is 500ms.
    r = _run(site, backend="http://127.0.0.1:1")
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "WARN" in out and "FR #9246 backend probe failed" in out
    assert "INFO Install-BobWebhooks done" in out


@NEED_PS
def test_fr9246_require_backend_fails_when_down(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    r = _run(site, "-RequireBackend", backend="http://127.0.0.1:1")
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode != 0, out
    assert "FR #9246 backend probe failed" in out


@NEED_PS
def test_fr9246_probe_ok_against_local_listener(tmp_path: Path):
    port = _free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _ReportHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        site = tmp_path / "irc-ntsa"
        site.mkdir()
        backend = f"http://127.0.0.1:{port}"
        r = _run(site, backend=backend)
        out = (r.stdout or "") + (r.stderr or "")
        assert r.returncode == 0, out
        assert "INFO FR #9246 backend probe OK" in out
        assert f"{backend}/bob/v1/report" in out
        assert "WARN FR #9246 backend probe failed" not in out
    finally:
        httpd.shutdown()
        httpd.server_close()
