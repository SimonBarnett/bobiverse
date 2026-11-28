"""Harvest #10101: promote digest #9991 IIS web.config heal lesson (FR #9992)."""
from pathlib import Path

from repo_layout import ROOT

JEEVES = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md"
LOG = ROOT / "common" / "docs" / "skill-harvest-log.md"


def test_fr10101_jeeves_harvested_lesson():
    text = JEEVES.read_text(encoding="utf-8")
    assert not JEEVES.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "9991" in text
    assert "9992" in text
    assert "Install-BobWebhooks.ps1" in text
    assert "models_put_forward" in text or "test_fr9992_models_put_probe_class" in text


def test_fr10101_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert not LOG.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "10101" in text
    assert "9991" in text
    assert "Install-BobWebhooks.ps1" in text
    assert "bobiverse-jeeves" in text


def test_fr10101_files_end_with_newline():
    for p in (JEEVES, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
