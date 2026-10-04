"""FR #1546: client id= pin, install DisplayName/log path, keepalive rate-limit."""
from __future__ import annotations

import re
import time
from pathlib import Path

import airc_console as ac
import airc_console_service as svc
from repo_layout import resolve


def test_parse_shell_request_honours_leading_id():
    req = ac.parse_shell_request("id=aabbccdd Write-Output ping")
    assert req.kind == "ps"
    assert req.job_id == "aabbccdd"
    assert req.body == "Write-Output ping"

    req2 = ac.parse_shell_request("id=deadbeef cmd: echo ok")
    assert req2.kind == "cmd"
    assert req2.job_id == "deadbeef"
    assert req2.body == "echo ok"


def test_format_shell_replies_uses_pinned_id():
    req = ac.parse_shell_request("id=aabbccdd Write-Output hi")
    out = ac.ShellOutcome(job_id=req.job_id, exit_code=0, stdout="hi\n", stderr="")
    lines = ac.format_shell_replies(out)
    assert lines[-1] == "DONE id=aabbccdd exit=0"
    assert any(x.startswith("out id=aabbccdd seq=") for x in lines)


def test_install_airc_console_expands_display_name_and_logs_under_packroot():
    script = resolve("scripts/Install-AircConsole.ps1")
    text = script.read_text(encoding="utf-8")
    assert "airc console (#{machine} IRC shell)" not in text
    assert "DisplayName', $displayName" in text or 'DisplayName", $displayName' in text or "$displayName" in text
    assert "Join-Path $packRoot 'logs'" in text or 'Join-Path $packRoot "logs"' in text
    assert "airc-console.log" in text
    # AppStdout must target install logs, not the old Grok agent folder.
    assert re.search(r"\$log\s*=\s*Join-Path \$logDir 'airc-console\.log'", text)
    assert "AppStdout" in text and "$log" in text
    assert re.search(r"DisplayName=\$displayName|INFO service DisplayName", text)


def test_info_prefixes_iso_timestamp(capsys):
    svc.info("INFO hello")
    out = capsys.readouterr().out.strip()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z INFO hello$", out)


def test_keepalive_rate_limited(capsys):
    svc._last_keepalive_log_mono = 0.0  # noqa: SLF001
    svc.info_keepalive("INFO keepalive PING sent")
    svc.info_keepalive("INFO keepalive PING sent")
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert "keepalive PING sent" in out[0]
    # Force interval elapsed
    svc._last_keepalive_log_mono = time.monotonic() - (svc._KEEPALIVE_LOG_INTERVAL_S + 1)  # noqa: SLF001
    svc.info_keepalive("INFO keepalive PING sent")
    out2 = capsys.readouterr().out.strip().splitlines()
    assert len(out2) == 1
