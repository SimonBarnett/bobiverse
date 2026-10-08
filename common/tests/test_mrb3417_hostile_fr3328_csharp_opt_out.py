"""Hostile MRB #3417 / FR #3328: C# CrashHook opt-out pins vs fleet-ops + airc skills."""
from __future__ import annotations

from repo_layout import resolve


def test_mrb3417_fleet_ops_and_airc_cite_fr3328_csharp_parity():
    fleet = resolve("common/.grok/skills/bobiverse-fleet-ops/SKILL.md").read_text(
        encoding="utf-8"
    )
    airc = resolve("airc/.grok/skills/bobiverse-airc/SKILL.md").read_text(encoding="utf-8")
    assert "FR #3328" in fleet
    assert "CrashHook" in fleet
    assert "BOB_CRASH_REPORT" in fleet
    assert "FR #3328" in airc
    assert "CrashHook" in airc
    assert fleet.startswith("\ufeff") is False
    assert airc.startswith("\ufeff") is False


def test_mrb3417_crashhook_gates_contiguous():
    text = resolve("bob/tray/dialogs/CrashHook.cs").read_text(encoding="utf-8-sig")
    assert "FR #3328" in text
    assert "class CrashReportPolicy" in text
    assert 'WriteSpool(title, body, sig, exeName, "local_only")' in text
    assert "if (!policy.Send) return;" in text
    assert "if (!policy.Send) return false;" in text
    assert "if (policy.Send) FlushSpool()" in text
    assert 'Environment.GetEnvironmentVariable("BOB_CRASH_REPORT")' in text
    assert "airc-shell-off" in text
    assert 'shell == "off"' in text
