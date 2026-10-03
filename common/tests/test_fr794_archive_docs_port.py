"""MRB #802 / FR #794: archived-doc port structure gates."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs" / "archive"
MANIFEST = ROOT / "docs" / "ARCHIVED_REPOS.md"
REPOS = ("agentic_build", "agentic_irc", "AgentMonitor", "gh-Jeeves", "bob-design-uat")


def test_archive_root_readme_exists():
    assert (ARCHIVE / "README.md").is_file()


def test_five_archived_repos_present():
    for name in REPOS:
        assert (ARCHIVE / name).is_dir(), name


def test_no_live_skill_md_under_archive():
    hits = list(ARCHIVE.rglob("SKILL.md"))
    assert hits == [], f"skill discovery must not see archive SKILL.md: {hits[:5]}"


def test_skill_copies_use_archived_suffix():
    skills = list(ARCHIVE.rglob("SKILL.archived.md"))
    assert len(skills) >= 1


def test_text_docs_carry_archived_copy_provenance():
    missing = []
    for repo in REPOS:
        for path in (ARCHIVE / repo).rglob("*.md"):
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if "ARCHIVED COPY" not in text:
                missing.append(str(path.relative_to(ROOT)))
    assert missing == [], missing[:20]


def test_manifest_has_fr794_map_and_counts():
    text = MANIFEST.read_text(encoding="utf-8-sig")
    assert "Archived document map (FR #794)" in text
    assert "493" in text
    for name in REPOS:
        assert name in text
    # no UTF-8 BOM on the live manifest
    raw = MANIFEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_ported_file_count_matches_claim():
    # exclude docs/archive/README.md (index only)
    files = [p for p in ARCHIVE.rglob("*") if p.is_file() and p.parent != ARCHIVE]
    assert len(files) == 493
