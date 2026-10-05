"""MRB #2359 hostile: FR #2354 Assert-BobiverseReleaseAssets gate presence."""
from __future__ import annotations

from pathlib import Path

from test_fr2354_release_assets import (
    missing_release_assets,
    required_release_assets,
)

ROOT = Path(__file__).resolve().parents[2]
PS1 = ROOT / "common/scripts/Assert-BobiverseReleaseAssets.ps1"
UAT = ROOT / "bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md"
OPS = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_mrb2359_assert_script_fail_closed_contract():
    raw = PS1.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = PS1.read_text(encoding="utf-8")
    assert "FR #2354" in text or "2354" in text
    assert "airc" in text and "jeeves" in text and "bob" in text
    assert ".sha256" in text
    assert "AllowMissing" in text
    assert "exit 1" in text
    assert "gh release view" in text


def test_mrb2359_helpers_match_script_naming():
    names = required_release_assets("1.2.3")
    assert names == [
        "bob-1.2.3.msi",
        "bob-1.2.3.msi.sha256",
        "airc-1.2.3.msi",
        "airc-1.2.3.msi.sha256",
        "jeeves-1.2.3.msi",
        "jeeves-1.2.3.msi.sha256",
    ]
    miss = missing_release_assets(["bob-1.2.3.msi"], "v1.2.3")
    assert "airc-1.2.3.msi" in miss
    assert "bob-1.2.3.msi" not in miss


def test_mrb2359_skills_and_harvest_mention_gate():
    for path in (UAT, OPS, LOG):
        text = path.read_text(encoding="utf-8")
        assert "2354" in text or "Assert-BobiverseReleaseAssets" in text
        assert "no-matching-asset" in text or "Assert-BobiverseReleaseAssets" in text
