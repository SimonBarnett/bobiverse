"""Hostile MRB #1660: skill-dba vendor stays under fleet-ops; audit and pin agree."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops"
DBA = FLEET / "skill-dba"
AUDIT = FLEET / "skill-vending-audit-2026-10-04.md"
PIN = DBA / "UPSTREAM-PIN.txt"
COMMON_PS1 = ROOT / "common/scripts/Bobiverse-Common.ps1"
PIN_SHA = "7bf3824ae5b6de3cf461bd22118658c4e371d5b4"


def test_mrb1660_no_free_floating_skill_dba_book():
    assert not (ROOT / "skill-dba").exists()
    assert not (ROOT / ".grok/skills/skill-dba").exists()
    assert not (ROOT / "common/.grok/skills/skill-dba").exists()
    assert DBA.is_dir()
    assert PIN.is_file()
    pin = PIN.read_text(encoding="utf-8-sig")
    assert "upstream=SimonBarnett/skill-dba" in pin
    assert PIN_SHA in pin


def test_mrb1660_audit_agrees_with_vendored_pin():
    text = AUDIT.read_text(encoding="utf-8-sig")
    assert "SimonBarnett/skill-dba" in text
    assert PIN_SHA in text
    assert "vendored under `skill-dba/`" in text or "skill-dba/" in text
    assert "No standalone `skill-dba` source was found" not in text


def test_mrb1660_twelve_books_and_sha_inventory():
    names = {
        "harvest-agent-skills",
        "mssql-backup-standard",
        "mssql-backup-audit",
        "mssql-backup-cutover",
        "mssql-weekly-backup-check",
        "mssql-instance-health-collect",
        "mssql-post-move-health",
        "mssql-disk-mount-layout-report",
        "mssql-deadlock-triage",
        "mssql-cost-capacity-review",
        "mssql-discover-registered-host",
        "mssql-agent-jobs-inventory",
    }
    assert len(names) == 12
    assert all((DBA / ".grok/skills" / n / "SKILL.md").is_file() for n in names)
    sha = (DBA / "SOURCE-SHA256.txt").read_text(encoding="utf-8-sig")
    assert PIN_SHA in sha or "SKILL.md" in sha
    common = COMMON_PS1.read_text(encoding="utf-8-sig")
    assert "bobiverse-fleet-ops" in common
    assert "Copy-Item -Path (Join-Path $from '*') -Destination $to -Recurse -Force" in common
