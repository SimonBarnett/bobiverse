"""Harvest #10104: promote digest #10019 MRB enablePullRequestAutoMerge lesson."""
from pathlib import Path

from repo_layout import ROOT

MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
LOG = ROOT / "common" / "docs" / "skill-harvest-log.md"


def test_fr10104_mrb_harvested_auto_merge_refuse():
    text = MRB.read_text(encoding="utf-8")
    assert not MRB.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "10104" in text
    assert "10019" in text
    assert "enablePullRequestAutoMerge" in text
    assert "merge-on-green pending" in text
    assert "FR #3948" in text


def test_fr10104_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert not LOG.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "10104" in text
    assert "10019" in text
    assert "enablePullRequestAutoMerge" in text
    assert "bobiverse-bob-job-mrb" in text


def test_fr10104_files_end_with_newline():
    for p in (MRB, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
