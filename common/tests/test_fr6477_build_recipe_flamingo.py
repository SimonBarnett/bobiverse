"""FR #6477: bobiverse BUILD recipe machine is flamingo (not retired ionos)."""
from __future__ import annotations

from pathlib import Path

import bobiverse_build as bb
import chair_commands as cc
from bobreport import fold_machine_id
from repo_layout import ROOT


def test_fr6477_recipe_machine_is_flamingo():
    recipe = bb.load_recipe(ROOT)
    assert recipe.machine == "flamingo"
    assert recipe.install_test.get("machine") == "flamingo"
    yml = (ROOT / ".bobiverse" / "build.yml").read_text(encoding="utf-8")
    assert "machine: flamingo" in yml
    assert "machine: ionos" not in yml


def test_fr6477_flamingo_fold_matches_local_id():
    # flamingo has no DIGEST_ID_FOLD alias; fold leaves it as flamingo.
    assert fold_machine_id("flamingo") == "flamingo"
    assert bb.fold_build_machine("flamingo") == "flamingo"
    assert bb.is_recipe_build_machine("flamingo", "flamingo") is True
    assert bb.is_recipe_build_machine("flamingo", "fl") is False
    assert bb.is_recipe_build_machine("flamingo", "ionos") is False
    assert bb.is_recipe_build_machine("flamingo", "win-mpre8vi4u6u") is False
    # Historical ionos alias remains for other recipes / tests.
    assert bb.is_recipe_build_machine("ionos", "win-mpre8vi4u6u") is True


def test_fr6477_decide_build_dry_run_targets_flamingo(tmp_path: Path):
    who = cc.Principal("owner", "simon", "simon")
    lock = bb.BuildLock(tmp_path / "build-locks.json", max_parallel=1)
    dec = bb.decide_build(
        who=who,
        body="!build dry-run SimonBarnett/bobiverse 2.0.0",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
    )
    assert dec is not None
    assert dec.dry_run is True
    assert dec.ok is True
    joined = "\n".join(dec.pm_lines)
    assert "machine=flamingo" in joined
    assert "dry-run" in joined.lower()
