"""FR #4950: pack artifacts must include airc-network-installer exe + sha256."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RECIPE = ROOT / ".bobiverse" / "build.yml"


def test_fr4950_build_yml_lists_network_installer_release_assets():
    data = yaml.safe_load(RECIPE.read_text(encoding="utf-8"))
    arts = list((data.get("pack") or {}).get("artifacts") or [])
    assert "airc-network-installer-{{version}}.exe" in arts
    assert "airc-network-installer-{{version}}.exe.sha256" in arts
    assert "airc-{{version}}.msi" in arts


def test_fr4950_assert_script_still_requires_installer():
    text = (ROOT / "common" / "scripts" / "Assert-BobiverseReleaseAssets.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "airc-network-installer-$ver.exe" in text
    assert "airc-network-installer-$ver.exe.sha256" in text
