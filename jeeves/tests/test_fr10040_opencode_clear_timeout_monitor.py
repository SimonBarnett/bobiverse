"""FR #10040 monitor fingerprint and check entry."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "monitor"))

import opencode_clear_timeout as clear_mod  # noqa: E402

MON = ROOT / "tools" / "monitor" / "opencode_clear_timeout.py"
WRAPPER = ROOT / "scripts" / "Test-JeevesMonitorOpencodeClearTimeout.ps1"


def test_fr10040_clear_timeout_and_stale_no_ack():
    for clear_line in (
        "opencode finish: Clear result=failed:TimeoutExpired\n",
        "opencode finish: Clear result=skipped:timeout\n",
    ):
        text = (
            clear_line
            + "relay: stale worktree offer #812 age_s=295 (no ACK yet)\n"
        )
        fp = clear_mod.scan_log(text, machine="marchhare", nick="marchhare-20008", turns_empty=True)
        assert fp == "opencode_clear_timeout_no_ack:marchhare:marchhare-20008"
    text = (
        "opencode finish: Clear result=skipped:timeout\n"
        "relay: stale worktree offer #812 age_s=295 (no ACK yet)\n"
    )
    assert clear_mod.scan_log(text, machine="marchhare", nick="n", turns_empty=False) is None
    assert clear_mod.scan_log("Clear result=ok", machine="m", nick="n", turns_empty=True) is None


def test_fr10040_wrapper_calls_the_check():
    text = WRAPPER.read_text(encoding="utf-8")
    assert "opencode_clear_timeout" in text
    assert "Invoke-JeevesMonitorCheck.ps1" in text


def test_fr10040_fixture_exits_finding(tmp_path: Path):
    seat = tmp_path / "marchhare-20008"
    seat.mkdir()
    (seat / "stdout.log").write_text(
        "opencode finish: Clear result=failed:TimeoutExpired\n"
        "relay: stale worktree offer #812 age_s=295 (no ACK yet)\n",
        encoding="utf-8",
    )
    (seat / "turns.jsonl").write_text("", encoding="utf-8")
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["JEEVES_OPENCODE_CLEAR_FIXTURE"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(MON)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 1, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["findings"] == ["opencode_clear_timeout_no_ack:marchhare:marchhare-20008"]
