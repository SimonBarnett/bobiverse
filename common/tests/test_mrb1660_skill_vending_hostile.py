"""Hostile MRB #1660: skill-vending audit must stay consistent with the pin and pack copy."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops"
AUDIT = FLEET / "skill-vending-audit-2026-10-04.md"
PIN = FLEET / "skill-dba" / "UPSTREAM-PIN.txt"
COMMON_PS1 = ROOT / "common/scripts/Bobiverse-Common.ps1"


def test_mrb1660_skill_dba_pin_only_under_fleet_ops():
    assert PIN.is_file(), "skill-dba UPSTREAM-PIN must live under bobiverse-fleet-ops"
    pin = PIN.read_text(encoding="utf-8-sig")
    assert "upstream=SimonBarnett/skill-dba" in pin
    assert "ref=" in pin
    # No free-floating top-level skill-dba book in this monorepo.
    assert not (ROOT / "skill-dba").exists()
    assert not (ROOT / ".grok/skills/skill-dba").exists()
    assert not (ROOT / "common/.grok/skills/skill-dba").exists()


def test_mrb1660_audit_matches_pin_and_sidecar():
    text = AUDIT.read_text(encoding="utf-8-sig")
    assert AUDIT.is_file()
    assert AUDIT.name == "skill-vending-audit-2026-10-04.md"
    assert "SimonBarnett/skill-dba" in text
    assert "UPSTREAM-PIN.txt" in text
    # Stale "no source found / do not invent" claim must not survive the pin commit.
    assert "No standalone `skill-dba` source was found" not in text


def test_mrb1660_worker_shared_copies_fleet_ops_recursively():
    common = COMMON_PS1.read_text(encoding="utf-8-sig")
    assert "'bobiverse-fleet-ops'" in common or '"bobiverse-fleet-ops"' in common
    # Agent folder sync copies every file under the shared skill dir (audit + pin).
    assert "Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force" in common
    assert "Shared = @(" in common and "bobiverse-fleet-ops" in common
