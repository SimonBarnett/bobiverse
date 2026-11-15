"""FR #7602: digest GET honors Timeout + ReadWriteTimeout under PS 5.1.

Invoke-WebRequest -TimeoutSec can hang past its budget on a hung or half-closed
socket. Invoke-BobDigestHttpGet uses HttpWebRequest with both Timeout and
ReadWriteTimeout so the call fails within timeout + 2s.

Generic host ids only; no secrets; no real machine names.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tray" / "src" / "Private" / "Invoke-BobDigestHttpGet.ps1"
GET_IRC = ROOT / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _ps(script: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _HangTcpServer:
    """Accept TCP, never send HTTP bytes (hung peer)."""

    def __init__(self) -> None:
        self.port = _free_port()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.port))
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self._stop = threading.Event()
        self._clients: list[socket.socket] = []
        self._th = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._th.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                c, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            c.settimeout(None)
            self._clients.append(c)
            # Hold the socket open; never respond.

    def stop(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        for c in self._clients:
            try:
                c.close()
            except OSError:
                pass
        self._th.join(timeout=2.0)


class _HalfCloseTcpServer:
    """Accept, send incomplete HTTP headers, then half-close (FIN) and stall."""

    def __init__(self) -> None:
        self.port = _free_port()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.port))
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self._stop = threading.Event()
        self._clients: list[socket.socket] = []
        self._th = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._th.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                c, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self._clients.append(c)
            try:
                # Incomplete response: status line only, no blank line / body.
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n")
                c.shutdown(socket.SHUT_WR)
            except OSError:
                try:
                    c.close()
                except OSError:
                    pass
                continue
            # Keep FD until stop so peer sees half-close, not full reset.

    def stop(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        for c in self._clients:
            try:
                c.close()
            except OSError:
                pass
        self._th.join(timeout=2.0)


class _OkHttpServer:
    """Minimal HTTP/1.1 200 JSON responder."""

    def __init__(self, body: bytes = b'{"ok":true}') -> None:
        self.port = _free_port()
        self.body = body
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.port))
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._th.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                c, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                c.settimeout(2.0)
                try:
                    c.recv(4096)
                except OSError:
                    pass
                hdr = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json; charset=utf-8\r\n"
                    f"Content-Length: {len(self.body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).encode("ascii")
                c.sendall(hdr + self.body)
            finally:
                try:
                    c.close()
                except OSError:
                    pass

    def stop(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        self._th.join(timeout=2.0)


def _invoke_helper(uri: str, timeout_sec: int = 2) -> tuple[str, float]:
    """Run Invoke-BobDigestHttpGet; return (stdout_line, wall_seconds)."""
    helper = str(HELPER).replace("'", "''")
    uri_ps = uri.replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
. '{helper}'
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {{
  $r = Invoke-BobDigestHttpGet -Uri '{uri_ps}' -TimeoutSec {int(timeout_sec)}
  Write-Output ('OK status=' + $r.StatusCode + ' text=' + $r.Text + ' elapsed=' + [Math]::Round($sw.Elapsed.TotalSeconds, 3))
}} catch {{
  Write-Output ('FAIL elapsed=' + [Math]::Round($sw.Elapsed.TotalSeconds, 3) + ' err=' + $_.Exception.Message)
}}
"""
    t0 = time.perf_counter()
    # Outer pytest timeout must exceed PS budget + 2s slack + process overhead.
    r = _ps(script, timeout=max(30, int(timeout_sec) + 15))
    wall = time.perf_counter() - t0
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    # Prefer last non-empty line from the helper.
    line = ""
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("OK ") or s.startswith("FAIL "):
            line = s
    if not line:
        line = out or f"empty rc={r.returncode}"
    return line, wall


def test_fr7602_helper_file_uses_httpwebrequest_not_iwr():
    assert HELPER.is_file(), "missing Invoke-BobDigestHttpGet.ps1"
    t = _txt(HELPER)
    assert "HttpWebRequest" in t
    assert "ReadWriteTimeout" in t
    assert "function Invoke-BobDigestHttpGet" in t
    assert "Invoke-WebRequest" not in t


def test_fr7602_read_bob_report_digest_http_uses_helper():
    t = _txt(GET_IRC)
    start = t.index("function Read-BobReportDigestHttp")
    end = t.index("function ConvertFrom-BobUtf8Json", start)
    body = t[start:end]
    assert "Invoke-BobDigestHttpGet" in body
    assert "Invoke-WebRequest" not in body
    assert "TimeoutSec" in body or "15" in body


def test_fr7602_update_bob_tray_digest_pools_uses_helper():
    t = _txt(HOVER)
    start = t.index("function Update-BobTrayDigestPools")
    # Next top-level function after Update-BobTrayDigestPools is large; bound by a marker.
    # Scan until a following function at column 0-ish after a reasonable window.
    rest = t[start:]
    m = re.search(r"\nfunction [A-Za-z-]+ ", rest[1:])
    body = rest[: (m.start() + 1)] if m else rest[:8000]
    assert "Invoke-BobDigestHttpGet" in body
    assert "Invoke-WebRequest" not in body


@needs_ps
def test_fr7602_hang_server_fails_within_timeout_plus_2s():
    srv = _HangTcpServer()
    srv.start()
    try:
        timeout_sec = 2
        line, wall = _invoke_helper(f"http://127.0.0.1:{srv.port}/", timeout_sec=timeout_sec)
        assert line.startswith("FAIL "), line
        m = re.search(r"elapsed=([0-9.]+)", line)
        assert m, line
        elapsed = float(m.group(1))
        assert elapsed <= timeout_sec + 2.0, (line, elapsed, wall)
        assert wall <= timeout_sec + 5.0, (line, wall)
    finally:
        srv.stop()


@needs_ps
def test_fr7602_half_close_server_fails_within_timeout_plus_2s():
    srv = _HalfCloseTcpServer()
    srv.start()
    try:
        timeout_sec = 2
        line, wall = _invoke_helper(f"http://127.0.0.1:{srv.port}/", timeout_sec=timeout_sec)
        assert line.startswith("FAIL "), line
        m = re.search(r"elapsed=([0-9.]+)", line)
        assert m, line
        elapsed = float(m.group(1))
        assert elapsed <= timeout_sec + 2.0, (line, elapsed, wall)
        assert wall <= timeout_sec + 5.0, (line, wall)
    finally:
        srv.stop()


@needs_ps
def test_fr7602_ok_server_returns_utf8_json():
    body = b'{"machines":{},"ok":true}'
    srv = _OkHttpServer(body=body)
    srv.start()
    try:
        line, wall = _invoke_helper(f"http://127.0.0.1:{srv.port}/bob/v1/report", timeout_sec=5)
        assert line.startswith("OK "), line
        assert "status=200" in line
        assert '"ok":true' in line or "ok" in line
        assert wall < 5.0
    finally:
        srv.stop()
