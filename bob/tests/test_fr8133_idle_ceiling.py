"""FR #8133: idle OpenCode seats must not arm the hard ceiling or unknown-job logs."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import opencode_turn_guard as g


def _launch(tmp_path: Path) -> str:
    spec = bw.build_launch("opencode", "agent", str(tmp_path), "hello", "opencode.exe", tmp_path)
    return next(v for p, v in spec.files.items() if str(p).endswith("launch-opencode.ps1"))


def test_fr8133_no_turn_or_ceiling_without_job(tmp_path: Path):
    text = _launch(tmp_path)
    assert "$script:ocHasJob = -not [string]::IsNullOrWhiteSpace([string]$jobKey)" in text
    assert "if ($script:ocHasJob) { Write-OpencodeTurnMarker 'turn_started'" in text
    assert "if ($script:ocHasJob) { Write-OpencodeTurnMarker 'turn_ended'" in text
    assert "if ($script:ocHasJob -and $stallMs -ge $hardCeilingMs)" in text
    assert "if ($script:ocHasJob -and $idleMs -ge $watchdogMs)" in text
    assert "if ($script:ocHasJob -and $env:BOB_OPENCODE_STDOUT_LOG" in text
    assert "Invoke-OpencodeRun $prompt '' ''" in text
    assert "opencode-ready: prompt (skill-dag MCP + seat prompt)" in text
    assert "opencode-ready: idle (FR #8133" not in text
    # Job inject still starts a watched run from the inject time.
    assert "Invoke-OpencodeRun $frame.line $frame.key $frame.dir" in text


def test_fr8133_ceiling_intake_skips_no_job():
    g._FILED.clear()
    calls: list[dict] = []

    def post(title, body, *, repo, sig, exe):
        calls.append({"title": title, "body": body, "sig": sig})

    for job in ("", "unknown-job-0", "unknown-job-0-redqueen-9444"):
        out = g.report_opencode_hard_ceiling(
            "redqueen", "redqueen-9444", job, 1800000, "hard ceiling", filer_post=post
        )
        assert out["skipped"] is True
        assert out.get("reason") == "no-job"
    assert calls == []
    # Real jobs still file once.
    ok = g.report_opencode_hard_ceiling(
        "redqueen",
        "redqueen-9444",
        "FR SimonBarnett/bobiverse#8133",
        1800000,
        "hard ceiling",
        filer_post=post,
    )
    assert ok["posted"] is True
    assert len(calls) == 1


def test_fr8133_agent_nonzero_exit_recycles(tmp_path: Path):
    """Acceptance: a dead agent must not keep !bored forever — recycle or give up."""
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "recycling seat via restart_agent (FR #7593)" in src
    assert 'self.restart_agent("agent-cli-nonzero-exit")' in src
    assert "hang-restart-limit" in src
