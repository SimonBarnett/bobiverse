"""FR #7999: gated real-Ergo test for the WSS -> register -> join -> shell-verb path.

Runs only when a Windows PowerShell host and an Ergo executable are available.
Discovers Ergo via ``AIRC_ERGO_EXE``/``ERGO_EXE`` or the ``Fetch-Ergo.ps1``
cache (``third_party/ergo``).  Skips cleanly otherwise.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import airc_console_service as svc

REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_ergo() -> str | None:
    for key in ("AIRC_ERGO_EXE", "ERGO_EXE"):
        v = os.environ.get(key)
        if v and Path(v).is_file():
            return v
    for rel in ("third_party/ergo/win64/ergo.exe", "third_party/ergo/ergo.exe"):
        cand = REPO_ROOT / rel
        if cand.is_file():
            return str(cand)
    return None


_ERGO = _find_ergo()

pytestmark = pytest.mark.skipif(
    os.name != "nt" or not shutil.which("powershell.exe") or not _ERGO,
    reason="FR #7999 Ergo integration needs Windows + PowerShell + an Ergo executable",
)


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _write_ircd_yaml(tmp: Path, plain_port: int, ws_port: int) -> Path:
    conf = tmp / "ircd.yaml"
    conf.write_text(
        f"server:\n"
        f"  name: wsirc.test\n"
        f"  listeners:\n"
        f"    \"127.0.0.1:{plain_port}\":\n"
        f"    \"127.0.0.1:{ws_port}\":\n"
        f"      websocket: true\n"
        f"  websockets:\n"
        f"    allowed-origins:\n"
        f"      - \"*\"\n"
        f"accounts:\n"
        f"  registration:\n"
        f"    enabled: true\n"
        f"    allow-before-connect: false\n"
        f"datastore:\n"
        f"  path: {tmp / 'ircd.db'}\n",
        encoding="utf-8",
    )
    return conf


def _wait_until(fn, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(0.1)
    return False


def _wait_for_port(port: int, timeout: float = 20.0) -> bool:
    def _open() -> bool:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close()
            return True
        except OSError:
            return False

    return _wait_until(_open, timeout)


class _IrcClient:
    def __init__(self, port: int) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.settimeout(5)
        self.buf = b""

    def send(self, line: str) -> None:
        self.sock.sendall((line.rstrip("\r\n") + "\r\n").encode("utf-8", errors="replace"))

    def read_line(self) -> str:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise EOFError("server closed")
            self.buf += chunk
        raw, self.buf = self.buf.split(b"\n", 1)
        return raw.decode("utf-8", errors="replace").rstrip("\r")

    def register(self, nick: str) -> None:
        self.send(f"NICK {nick}")
        self.send(f"USER {nick} 0 * :{nick}")
        while True:
            line = self.read_line()
            if line.upper().startswith("PING "):
                self.send("PONG " + line[5:])
                continue
            if " 001 " in f" {line} ":
                return

    def join(self, channel: str) -> None:
        self.send(f"JOIN {channel}")
        while True:
            line = self.read_line()
            if " JOIN " in f" {line} " and channel.lower() in line.lower():
                return

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def _collect_until_done(client: _IrcClient, timeout: float) -> str:
    out: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        client.sock.settimeout(max(0.5, deadline - time.monotonic()))
        try:
            line = client.read_line()
        except OSError:
            break
        out.append(line)
        if "DONE id=" in line:
            break
    return "\n".join(out)


def test_ergo_wss_shell_roundtrip(tmp_path, monkeypatch):
    plain_port = _free_port()
    ws_port = _free_port()
    conf = _write_ircd_yaml(tmp_path, plain_port, ws_port)
    proc = subprocess.Popen(
        [_ERGO, "run", "--conf", str(conf)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_for_port(plain_port), "Ergo plain listener did not come up"
        assert _wait_for_port(ws_port), "Ergo websocket listener did not come up"

        machine = "tm"
        op = _IrcClient(plain_port)
        try:
            op.register("operator")
            op.join(f"#{machine}")
        finally:
            pass

        logs: list[str] = []
        monkeypatch.setattr(svc, "info", lambda m: logs.append(m))
        monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "dummy-server-pass")
        args = svc.build_arg_parser().parse_args(
            [
                "--machine", machine,
                "--home", str(tmp_path / "home"),
                "--shop-mode", "registered",
                "--no-sasl",
                "--transport", "wss",
                "--ws-url", f"ws://127.0.0.1:{ws_port}/",
            ]
        )
        service = svc.AircConsoleService(args)
        runner = threading.Thread(target=service.run, daemon=True)
        runner.start()
        try:
            assert _wait_until(
                lambda: bool(service._registered) and bool(getattr(service.members, "synced", False)),
                30.0,
            ), "service did not register and sync NAMES over WSS"
            assert any("registered via transport=wss" in l for l in logs)
            op.send(f"PRIVMSG {machine}_console :Write-Output 'hello-fr7999'")
            reply = _collect_until_done(op, timeout=30.0)
            assert "hello-fr7999" in reply
            assert "DONE id=" in reply
        finally:
            service._stop.set()
            service.prepare_stop(reason="test-done")
            runner.join(5.0)
            op.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
