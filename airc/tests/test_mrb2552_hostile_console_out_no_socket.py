# MRB #2552 hostile gates for FR #2551 console-out ConnectionError swallow.
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_console_service as svc
import airc_jobs as aj

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
CONSOLE = (ROOT / "scripts" / "airc_console.py").read_text(encoding="utf-8")
JOBS = (ROOT / "scripts" / "airc_jobs.py").read_text(encoding="utf-8")
PRODUCT_TEST = Path(__file__).with_name("test_fr2551_console_out_no_socket.py").read_bytes()


def test_product_test_file_utf8_no_bom():
    assert not PRODUCT_TEST.startswith(b"\xef\xbb\xbf")
    assert b"JobProtocol(" in PRODUCT_TEST
    assert b"JobProtocolHandler" not in PRODUCT_TEST


def test_on_console_out_source_catches_connection_error_and_forces_reconnect():
    assert "except ConnectionError as e:" in SERVICE
    assert "console-out-send-err" in SERVICE
    idx = SERVICE.index("def _on_console_out")
    end = SERVICE.index("\n    def ", idx + 1)
    chunk = SERVICE[idx:end]
    assert "except ConnectionError" in chunk
    assert "self._force_reconnect = True" in chunk
    # Narrow catch: do not blanket-swallow Exception in _on_console_out.
    assert "except Exception" not in chunk


def test_shell_and_jobs_emit_defend_in_depth():
    assert "class ShellJobRunner" in CONSOLE
    assert "class JobProtocol" in JOBS
    assert "class JobProtocolHandler" not in JOBS
    for src, marker in ((CONSOLE, "class ShellJobRunner"), (JOBS, "class JobProtocol")):
        class_idx = src.index(marker)
        emit_idx = src.index("def _emit", class_idx)
        chunk = src[emit_idx : emit_idx + 350]
        assert "except ConnectionError" in chunk
        assert "FR #2551" in chunk


def test_send_raises_connection_error_no_socket_and_wraps_oserror(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    s = svc.AircConsoleService(args)
    s.sock = None
    raised = False
    try:
        s.send("PRIVMSG bob-tm :hi")
    except ConnectionError as e:
        raised = True
        assert "no socket" in str(e)
    assert raised

    class _DeadSock:
        def sendall(self, data):  # noqa: ANN001
            raise OSError(10054, "connection reset")

    s.sock = _DeadSock()
    raised2 = False
    try:
        s.send("PRIVMSG bob-tm :hi")
    except ConnectionError as e:
        raised2 = True
        assert "send failed" in str(e)
    assert raised2


def test_shell_emit_and_jobs_emit_do_not_raise(tmp_path):
    def boom(nick: str, line: str) -> None:
        raise ConnectionError("send: no socket")

    ac.ShellJobRunner(on_reply=boom, wait=False)._emit("bob-tm", "out id=abcd1234 seq=1 hi")
    store = aj.JobStore(tmp_path / "jobs")
    aj.JobProtocol(store=store, on_reply=boom, machine="tm")._emit(
        "bob-tm", "DONE id=abcd1234 exit=0"
    )
