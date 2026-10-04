from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "common/.grok/skills/bobiverse-fleet-ops/skill-vending-audit-2026-10-04.md"


def test_owner_books_and_flow_diagrams_are_canonical():
    required = {
        "bob/.grok/skills/bobiverse-bob-worker/SKILL.md",
        "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md",
        "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md",
        "bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md",
        "common/.grok/skills/bobiverse-fleet-ops/SKILL.md",
        "common/.grok/skills/harvest-agent-skills/SKILL.md",
        "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md",
    }
    for rel in required:
        assert (ROOT / rel).is_file(), rel
    text = AUDIT.read_text(encoding="utf-8-sig")
    assert "b15182a" in text and "PR #1491" in text
    assert "skill-dba` at pinned main commit `7bf3824ae5b6de3cf461bd22118658c4e371d5b4" in text
    assert text.count("```mermaid") >= 4
    for section in ("FR acceptance flow", "MRB acceptance flow", "UAT acceptance flow"):
        assert section in text


def test_installers_copy_complete_shared_skill_books():
    common = (ROOT / "common/scripts/Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
    bob = (ROOT / "bob/scripts/Install-Bob.ps1").read_text(encoding="utf-8-sig")
    jeeves = (ROOT / "jeeves/scripts/Install-Jeeves.ps1").read_text(encoding="utf-8-sig")
    for text in (bob, jeeves):
        assert "Install-BobiverseAgentLayer" in text
        assert "Install-BobiverseSkills" in text
    assert "Get-BobiverseSkillNames" in common
    assert "bobiverse-fleet-ops" in common
    assert "Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force" in common


def test_skill_dba_is_vendored_at_pinned_upstream_ref():
    root = ROOT / "common/.grok/skills/bobiverse-fleet-ops/skill-dba"
    pin = (root / "UPSTREAM-PIN.txt").read_text(encoding="utf-8")
    assert "SimonBarnett/skill-dba" in pin
    assert "7bf3824ae5b6de3cf461bd22118658c4e371d5b4" in pin
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
    assert all((root / ".grok/skills" / name / "SKILL.md").is_file() for name in names)
    assert (root / "SOURCE-SHA256.txt").is_file()
    manifest = (root / "docs/skill-sources/MANIFEST.md").read_text(encoding="utf-8")
    for rel in ("scripts/Invoke-BackupAudit.ps1", "scripts/Invoke-LiveAudit.ps1", "scripts/Invoke-PostMoveHealth.ps1", "scripts/dba_instance_health_collect.sql", "config/instances.example.json"):
        assert rel in manifest
