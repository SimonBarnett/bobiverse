"""FR #9496: prior-clean scan failure must not abort ear connect (nssm restart loop).

When CIM/WMI listing fails after FR #9236 retries, clean_crashed_priors continues
connect with a WARN. WMIC fallback is preferred when Get-CimInstance times out.
No machine names in this file.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import prior_irc


def test_fr9496_clean_crashed_priors_no_systemexit_on_scan_fail(monkeypatch):
    import irc_agent

    monkeypatch.delenv("BOB_IRC_SKIP_PRIOR_CLEAN", raising=False)

    class FakeResult:
        scanned = False
        scan_attempts = 3

    monkeypatch.setattr(
        prior_irc,
        "clean_priors",
        lambda *a, **k: FakeResult(),
    )
    import sys

    sys.modules["prior_irc"] = prior_irc
    try:
        irc_agent.clean_crashed_priors("bob-test", str(Path.home() / ".bobiverse"), once=False)
    except SystemExit as exc:
        raise AssertionError(f"must not SystemExit on scan fail, got {exc}") from exc


def test_fr9496_windows_list_falls_back_to_wmic(monkeypatch):
    calls: list[str] = []

    def fake_check_output(cmd, **kwargs):
        calls.append(str(cmd[0]).lower())
        if "powershell" in str(cmd[0]).lower():
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)
        # WMIC LIST format
        return (
            "CommandLine=C:\\ai\\bob\\scripts\\bob-ear.exe --nick bob-test --home C:\\h\r\n"
            "ProcessId=4242\r\n"
            "\r\n"
        )

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)
    rows = prior_irc._list_windows()
    assert any("powershell" in c for c in calls)
    assert any("wmic" in c for c in calls)
    assert rows == [(4242, "C:\\ai\\bob\\scripts\\bob-ear.exe --nick bob-test --home C:\\h")]


def test_fr9496_source_pins_fail_open_and_wmic():
    root = Path(__file__).resolve().parents[2]
    agent = (root / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    prior = (root / "common" / "scripts" / "prior_irc.py").read_text(encoding="utf-8")
    assert "FR #9496 fail-open" in agent
    assert "scan-failed continuing connect" in agent
    assert "SystemExit(1)" not in agent[agent.index("def clean_crashed_priors") : agent.index("def main")]
    assert "fallback=wmic" in prior
    assert "_list_windows_wmic" in prior
