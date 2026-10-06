"""FR #75: airc PowerShell default shell, psb64, IRC chunking, DONE exit contract."""
from __future__ import annotations

import base64
import os
import shutil
import sys
from pathlib import Path

import pytest

import airc_console as ac


pytestmark = pytest.mark.skipif(
    os.name != "nt" or not shutil.which("powershell.exe"),
    reason="FR #75 requires Windows PowerShell 5.1",
)


def _utf16_b64(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _utf8_b64(script: str) -> str:
    return base64.b64encode(script.encode("utf-8")).decode("ascii")


def test_default_powershell_argv_uses_noprofile():
    req = ac.parse_shell_request("Write-Output hi")
    assert req.kind == "ps"
    argv = ac.build_shell_argv(req)
    assert argv[0].lower().endswith("powershell.exe")
    assert "-NoProfile" in argv
    assert "-EncodedCommand" in argv


def test_cmd_escape_uses_comspec(monkeypatch):
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    req = ac.parse_shell_request("cmd: echo %COMSPEC%")
    assert req.kind == "cmd"
    argv = ac.build_shell_argv(req)
    assert argv[0].lower().endswith("cmd.exe")
    assert "/c" in [a.lower() for a in argv]
    # FR #2580 prefixes chcp 65001 so non-ASCII cmd stdout survives capture.
    assert any("echo %COMSPEC%" in a for a in argv)
    assert any(a.lower().startswith("chcp 65001") or "chcp 65001" in a.lower() for a in argv)


def test_psb64_roundtrip_computername():
    script = "Write-Output $env:COMPUTERNAME"
    req = ac.parse_shell_request("psb64:" + _utf16_b64(script))
    assert req.kind == "psb64"
    out = ac.run_shell_request(req, timeout_s=30)
    assert out.exit_code == 0
    host = (os.environ.get("COMPUTERNAME") or "").strip()
    assert host
    assert host.lower() in out.stdout.lower()


def test_psb64_accepts_utf8_payload_and_runs():
    script = "Write-Output 'utf8-ok'"
    req = ac.parse_shell_request("psb64:" + _utf8_b64(script))
    out = ac.run_shell_request(req, timeout_s=30)
    assert out.exit_code == 0
    assert "utf8-ok" in out.stdout


def test_plain_ps_noprofile_ordered_output_and_exit():
    req = ac.parse_shell_request("Write-Output 'a'; Write-Output 'b'; exit 0")
    out = ac.run_shell_request(req, timeout_s=30)
    assert out.exit_code == 0
    lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    assert lines[:2] == ["a", "b"]
    records = ac.format_shell_replies(out)
    assert records[-1] == f"DONE id={out.job_id} exit=0"
    assert any(r.startswith(f"out id={out.job_id} seq=1 ") for r in records)


def test_stderr_and_nonzero_exit_represented():
    req = ac.parse_shell_request(
        "Write-Error 'boom'; exit 7"
    )
    out = ac.run_shell_request(req, timeout_s=30)
    assert out.exit_code == 7
    records = ac.format_shell_replies(out)
    assert records[-1] == f"DONE id={out.job_id} exit=7"
    assert any(r.startswith("err id=") for r in records)


def test_long_output_is_chunked_not_silently_clipped():
    # One long line longer than legacy 400-char clip
    payload = "X" * 900
    req = ac.parse_shell_request(f"Write-Output '{payload}'")
    out = ac.run_shell_request(req, timeout_s=30)
    assert out.exit_code == 0
    records = ac.format_shell_replies(out, irc_limit=ac.IRC_SAFE_PAYLOAD)
    body = "".join(
        r.split(" ", 3)[-1] for r in records if r.startswith("out ")
    )
    assert payload in body
    assert all(len(r) <= ac.IRC_SAFE_PAYLOAD for r in records[:-1])
    assert records[-1].startswith("DONE id=")


def test_malformed_and_oversized_psb64_rejected():
    with pytest.raises(ac.ShellRequestError, match="malformed"):
        ac.parse_shell_request("psb64:%%%not-base64%%%")
    huge = "A" * (ac.PSB64_MAX_CHARS + 10)
    with pytest.raises(ac.ShellRequestError, match="too large"):
        ac.parse_shell_request("psb64:" + huge)


def test_core_help_mentions_ps_and_psb64():
    auth = ac.AuthPolicy(operators={"bob-tm"}, machine="tm")
    replies: list[tuple[str, str]] = []
    runner = ac.ShellJobRunner(on_reply=lambda n, line: replies.append((n, line)))
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        shell_runner=runner,
    )
    hr = core.handle_raw(":bob-tm!u@h PRIVMSG tm_console :.help")
    assert hr is not None and hr.reply
    assert "powershell" in hr.reply.lower() or "psb64" in hr.reply.lower()
    assert "cmd:" in hr.reply


def test_core_runs_plain_command_with_done_via_runner(monkeypatch):
    auth = ac.AuthPolicy(operators={"bob-tm"}, machine="tm")
    replies: list[str] = []
    runner = ac.ShellJobRunner(on_reply=lambda n, line: replies.append(line), wait=True)
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        shell_runner=runner,
    )
    hr = core.handle_raw(":bob-tm!u@h PRIVMSG tm_console :Write-Output 'fr75'")
    assert hr is not None
    assert hr.action == "shell"
    assert any(r.endswith("fr75") or " fr75" in r for r in replies)
    assert any(r.startswith("DONE id=") and r.endswith("exit=0") for r in replies)


def test_service_console_out_chunks_instead_of_hard_clip(tmp_path, monkeypatch):
    import airc_console_service as svc

    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    s = svc.AircConsoleService(args)
    sent: list[str] = []
    # FR #2655: drain_out_queue passes flood=; stub must accept **kw.
    s.send_privmsg = lambda target, text, **_kw: sent.append(f"{target}:{text}")  # type: ignore[assignment]
    long = "Z" * 900
    s._on_console_out("bob-tm", long)
    assert len(sent) >= 2
    assert all(len(x.split(":", 1)[1]) <= ac.IRC_SAFE_PAYLOAD for x in sent)
    assert "".join(x.split(":", 1)[1] for x in sent) == long
