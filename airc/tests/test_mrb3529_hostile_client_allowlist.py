"""docs/mrb-3529 hostile pins for FR #3514 / PR #3529 client allow-list payload."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"
POST = ROOT / "common" / "docs" / "post-install.md"

KEEP = (
    "Bobiverse-Common.ps1",
    "Install-Airc.ps1",
    "Report-BobiverseIntakeIssue.ps1",
    "crash_report.py",
    "airc_console_service.py",
)
GONE = (
    "jeeves_main.py",
    "gitclaim.py",
    "bob_worker.py",
    "Install-Jeeves.ps1",
    "Install-Bob.ps1",
)


def test_allowlist_helper_keeps_runtime_and_drops_union():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Get-BobiverseAircClientAllowedScriptNames" in t
    assert "function Remove-BobiverseAircClientExtraPayload" in t
    assert "FR #3514" in t
    assert "FR #3582" in t
    assert r"config\fleet-operators.txt" in t
    for name in KEEP:
        assert name in t, name
    # Allow-list body must not name foreign product scripts as keepers.
    i = t.find("function Get-BobiverseAircClientAllowedScriptNames")
    j = t.find("function Remove-BobiverseAircClientExtraPayload", i)
    chunk = t[i:j]
    for name in GONE:
        assert name not in chunk, name


def test_install_branches_client_allowlist_vs_workstation_deny():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "Remove-BobiverseAircClientExtraPayload" in t
    assert "Remove-BobiverseAircWorkstationAgentPayload" in t
    assert "prof -eq 'client'" in t
    assert "FR #3514" in t


def test_skill_and_post_install_cite_allowlist_and_keep_3511():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3514" in skill
    assert "Remove-BobiverseAircClientExtraPayload" in skill or "allow-list" in skill.lower()
    assert "FR #3511" in skill  # keep-both after behind-main skill merge
    assert "lost-control" in skill or "ChannelMemberMap" in skill
    assert "FR #3582" in skill
    assert "fleet-operators" in skill
    post = POST.read_text(encoding="utf-8")
    assert "FR #3514" in post
    assert "FR #3582" in post
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
