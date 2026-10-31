"""FR #5519: NETWORK/EXTENSION/LEGION IRC CONT fallback without DCCLISTEN."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_console_service as svc
from airc_auth_helpers import ops_auth
from airc_jobs import JobProtocol, JobStore

ROOT = Path(__file__).resolve().parents[2]


def _core(tmp_path, **kw):
    return ac.AircConsoleCore(
        machine="tm",
        auth=ops_auth("op", channel="#tm"),
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=lambda *_a, **_k: None),
        job_protocol=JobProtocol(JobStore(tmp_path / "home"), machine="tm", airc_running=True),
        **kw,
    )


def test_fr5519_network_emit_cont_without_dcclisten(tmp_path):
    emitted: list[dict] = []
    core = _core(tmp_path)
    svc.attach_verb_log_hooks(
        core,
        send_fn=lambda *_a, **_k: None,
        emit_fn=emitted.append,
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd NETWORK diag")
    assert hr is not None and hr.action == "network"
    assert "NETWORK accepted" in (hr.reply or "")
    assert emitted, "IRC fallback must emit CONT/DONE when DCCLISTEN is absent"
    lines = "\n".join(str(x) for x in (emitted[0].get("lines") or []))
    assert "CONT id=aabbccdd" in lines
    assert "DONE id=aabbccdd" in lines
    assert emitted[0].get("via") == "irc"


def test_fr5519_extension_emit_without_dcclisten(tmp_path):
    emitted: list[dict] = []
    core = _core(tmp_path)
    svc.attach_verb_log_hooks(core, send_fn=lambda *_a, **_k: None, emit_fn=emitted.append)
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd EXTENSION status")
    assert hr is not None
    if hr.action == "capability_deny":
        return
    assert hr.action == "extension"
    assert emitted
    lines = "\n".join(str(x) for x in (emitted[0].get("lines") or []))
    assert "CONT id=aabbccdd" in lines or "DONE id=aabbccdd" in lines


def test_fr5519_service_handle_sends_network_reply_and_hooks():
    src = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert "attach_verb_log_hooks" in src
    assert "_log_send" in src and "_log_emit" in src
    assert '"network"' in src and '"legion"' in src and '"extension"' in src
    # handle_line must send those verb replies (not drop them).
    block = src.split("elif hr.action in")[1].split("elif hr.action")[0]
    assert "network" in block and "legion" in block and "extension" in block
    assert not (ROOT / "airc" / "scripts" / "airc_console_service.py").read_bytes().startswith(
        b"\xef\xbb\xbf"
    )
    assert not (ROOT / "airc" / "scripts" / "airc_console.py").read_bytes().startswith(b"\xef\xbb\xbf")
