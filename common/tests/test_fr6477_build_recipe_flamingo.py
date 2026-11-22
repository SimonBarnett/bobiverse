"""FR #6477 / #8653: bobiverse BUILD recipe machine is the live chair host walrus."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import builds_catalog as bc
import chair_commands as cc
from bobreport import fold_machine_id
from repo_layout import ROOT


def _cat():
    return [
        bc.BuildCatalogEntry(
            name="Bobiverse",
            yml="SimonBarnett/bobiverse:.bobiverse/build.yml",
            output=r"D:\Temp\bobiverse-build",
            install="fleet",
        )
    ]


def test_fr6477_recipe_machine_is_walrus():
    recipe = bb.load_recipe(ROOT)
    assert recipe.machine == "walrus"
    assert recipe.install_test.get("machine") == "walrus"
    yml = (ROOT / ".bobiverse" / "build.yml").read_text(encoding="utf-8")
    assert "machine: walrus" in yml
    assert "machine: ionos" not in yml
    assert "machine: flamingo" not in yml


def test_fr6477_flamingo_fold_matches_local_id():
    # flamingo has no DIGEST_ID_FOLD alias; fold leaves it as flamingo.
    assert fold_machine_id("flamingo") == "flamingo"
    assert bb.fold_build_machine("flamingo") == "flamingo"
    assert bb.is_recipe_build_machine("flamingo", "flamingo") is True
    assert bb.is_recipe_build_machine("flamingo", "fl") is False
    assert bb.is_recipe_build_machine("flamingo", "ionos") is False
    assert bb.is_recipe_build_machine("flamingo", "win-mpre8vi4u6u") is False
    # FR #8697: historical ionos alias folds to walrus (not win-mpre).
    assert bb.is_recipe_build_machine("ionos", "walrus") is True
    assert bb.is_recipe_build_machine("ionos", "win-mpre8vi4u6u") is False


def test_fr6477_decide_build_dry_run_targets_flamingo(tmp_path: Path):
    who = cc.Principal("owner", "simon", "simon")
    lock = bb.BuildLock(tmp_path / "build-locks.json", max_parallel=1)
    dec = bb.decide_build(
        who=who,
        body="!build dry-run 1 2.0.0",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        catalog_entries=_cat(),
    )
    assert dec is not None
    assert dec.dry_run is True
    assert dec.ok is True
    joined = "\n".join(dec.pm_lines)
    assert "machine=walrus" in joined
    assert "dry-run" in joined.lower()
