"""FR #147: skills must forbid dumping nssm AppEnvironmentExtra values."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
TROUBLE = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"
UAT = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-uat" / "SKILL.md"


def test_fleet_ops_forbids_raw_appenvironmentextra_dump():
    text = FLEET.read_text(encoding="utf-8")
    assert "FR #147" in text
    assert "AppEnvironmentExtra" in text
    assert "key names only" in text.lower() or "KEY names only" in text
    assert "AGENTIC_IRC_PASSWORD" in text
    assert "split" in text.lower() and "=" in text


def test_troubleshooting_and_uat_point_at_keys_only_rule():
    for path in (TROUBLE, UAT):
        assert path.is_file(), path
        text = path.read_text(encoding="utf-8")
        assert "FR #147" in text
        assert "AppEnvironmentExtra" in text
