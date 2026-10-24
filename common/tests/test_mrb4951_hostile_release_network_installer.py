"""MRB #4951 hostile: pack.artifacts is the upload list; installer names match Assert."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RECIPE = ROOT / ".bobiverse" / "build.yml"
ASSERT = ROOT / "common" / "scripts" / "Assert-BobiverseReleaseAssets.ps1"


def test_mrb4951_pack_artifacts_has_eight_named_release_files():
    data = yaml.safe_load(RECIPE.read_text(encoding="utf-8"))
    arts = list((data.get("pack") or {}).get("artifacts") or [])
    assert arts.count("airc-network-installer-{{version}}.exe") == 1
    assert arts.count("airc-network-installer-{{version}}.exe.sha256") == 1
    assert len(arts) == 8
    # Runner uploads exactly this list (bobiverse_build pack:artifacts / assets=).
    build_py = (ROOT / "common" / "scripts" / "bobiverse_build.py").read_text(encoding="utf-8")
    assert 'self.recipe.pack or {}).get("artifacts")' in build_py
    assert "pack:artifacts" in build_py


def test_mrb4951_assert_and_yaml_share_the_same_installer_basename():
    text = ASSERT.read_text(encoding="utf-8")
    assert "airc-network-installer-$ver.exe" in text
    assert "airc-network-installer-$ver.exe.sha256" in text
    assert "if ($Products -contains 'airc')" in text
