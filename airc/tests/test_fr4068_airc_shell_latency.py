"""FR #4068: shell-done timing + documented batch-capture / FLOOD_S latency."""
from __future__ import annotations

import time
from pathlib import Path

import airc_console as ac
from repo_layout import ROOT

SKILL = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
SVC = ROOT / "airc/scripts/airc_console_service.py"


def _utf8(p: Path) -> str:
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {p}"
    return raw.decode("utf-8")


def test_fr4068_shell_done_metrics_callback(monkeypatch):
    """Command path reports elapsed_ms + reply_lines after batch capture."""
    metrics: list[tuple] = []

    def fake_run(req, *, timeout_s=30.0, cwd=None):
        time.sleep(0.01)
        return ac.ShellOutcome(job_id=req.job_id, exit_code=0, stdout="line-a\nline-b\n", stderr="")

    monkeypatch.setattr(ac, "run_shell_request", fake_run)
    runner = ac.ShellJobRunner(
        on_reply=lambda nick, line: None,
        wait=True,
        on_shell_done=lambda nick, jid, elapsed_s, replies, exit_code: metrics.append(
            (nick, jid, elapsed_s, replies, exit_code)
        ),
    )
    runner.start("slab-op", "id=abcd1234 Write-Output x")
    assert len(metrics) == 1
    nick, jid, elapsed_s, replies, exit_code = metrics[0]
    assert nick == "slab-op"
    assert jid == "abcd1234"
    assert exit_code == 0
    assert replies >= 3  # two out + DONE
    assert elapsed_s >= 0.0


def test_fr4068_troubleshooting_documents_batch_capture_and_flood():
    t = _utf8(SKILL)
    assert "FR #4068" in t
    assert "subprocess.run" in t or "capture_output" in t or "batch capture" in t.lower()
    assert "FLOOD_S" in t
    assert "cmd: dir" in t
    assert "TimeoutSec" in t or "timeout" in t.lower()


def test_fr4068_service_wires_shell_done_log():
    src = _utf8(SVC)
    assert "on_shell_done" in src
    assert "shell-done" in src
