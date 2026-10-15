"""docs/mrb-4298 hostile pin for FR #4297 harvest tip overlay."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_harvest_overlay_helpers_and_sync_order():
    common = (ROOT / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8")
    assert "function Sync-BobiverseScriptTipFromOrigin" in common
    assert "function Sync-BobiverseHarvestScriptsFromOrigin" in common
    assert "function Sync-BobiverseUpdaterFromOrigin" in common
    assert "Invoke-BobiverseHarvest.ps1" in common
    assert "Report-BobiverseIntakeIssue.ps1" in common
    assert "ExistingPrUrl" in common or "ContentMustMatch" in common

    sync = (ROOT / "scripts" / "Sync-BobiverseFromRepo.ps1").read_text(encoding="utf-8")
    assert "Sync-BobiverseUpdaterFromOrigin" in sync
    assert "Sync-BobiverseHarvestScriptsFromOrigin" in sync
    # harvest overlay after updater
    assert sync.index("Sync-BobiverseUpdaterFromOrigin") < sync.index(
        "Sync-BobiverseHarvestScriptsFromOrigin"
    )

    skill = (ROOT / ".grok" / "skills" / "harvest" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #4297" in skill
    assert r"common\scripts" in skill or "common/scripts" in skill
    assert "ComposeOnly" in skill
    assert "\ufeff" not in skill

    post = (ROOT / "docs" / "post-install.md").read_text(encoding="utf-8")
    assert "FR #4297" in post
    assert "Sync-BobiverseHarvestScriptsFromOrigin" in post

    fr_test = (ROOT / "tests" / "test_fr4297_sync_harvest_from_tip.py").read_text(
        encoding="utf-8"
    )
    assert "Sync-BobiverseHarvestScriptsFromOrigin" in fr_test
    for p in (
        ROOT / "scripts" / "Bobiverse-Common.ps1",
        ROOT / "scripts" / "Sync-BobiverseFromRepo.ps1",
        ROOT / "tests" / "test_fr4297_sync_harvest_from_tip.py",
    ):
        text = p.read_text(encoding="utf-8")
        assert "<<<<<<<" not in text