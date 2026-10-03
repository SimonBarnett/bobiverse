"""FR #806: archive-richer hand-merge keeps CAST IRON + intake on harvest skill."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "common" / ".grok" / "skills" / "harvest-agent-skills" / "SKILL.md"
SPEC = ROOT / "common" / "docs" / "functional-spec.md"
README = ROOT / "README.md"
ERGO = ROOT / "common" / "third_party" / "ergo" / "README.txt"
MANIFEST = ROOT / "docs" / "ARCHIVED_REPOS.md"


def test_harvest_skill_cast_iron_and_intake_commands():
    text = SKILL.read_text(encoding="utf-8")
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert "CAST IRON" in text
    assert "Report-BobiverseIntakeIssue.ps1" in text
    assert "Invoke-BobiverseHarvest.ps1" in text
    assert "POST https://irc.ntsa.uk/bob/v1/intake" in text
    assert "SimonBarnett/bobiverse" in text
    # archived homes must not be live intake targets
    assert "github: https://github.com/SimonBarnett/agentic_build" not in text
    assert "File intake against archived" in text or "archived superseded" in text.lower()


def test_functional_spec_has_per_repo_uat_and_visual_gates():
    text = SPEC.read_text(encoding="utf-8")
    assert "per REPO" in text or "UAT owner/repo#0" in text
    assert "G1" in text and "G2" in text and "G3" in text


def test_readme_points_at_archive_not_as_live_runbook():
    text = README.read_text(encoding="utf-8")
    assert "docs/archive" in text
    assert "honesty box" in text.lower() or "Harvest" in text


def test_ergo_readme_describe_only_no_secret():
    text = ERGO.read_text(encoding="utf-8")
    assert "DESCRIBE ONLY" in text
    assert "NOT stored in git" in text
    assert "password=" not in text.lower()


def test_manifest_marks_fr806_merges():
    text = MANIFEST.read_text(encoding="utf-8")
    assert text.count("FR #806") >= 10
    assert "archive richer / newer\" marks documents to merge by hand" not in text
