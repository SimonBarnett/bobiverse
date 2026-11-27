"""FR #9777: !build recipe packs the IRCD payload without www or a chair MSI."""
from __future__ import annotations

import json

from repo_layout import ROOT

RECIPE = ROOT / ".bobiverse" / "build-jeeves-ircd.yml"
PACK = ROOT / "jeeves" / "scripts" / "Pack-BobIrcdPayload.ps1"
CATALOG = ROOT / "common" / "defaults" / "builds-catalog.example.json"


def test_fr9777_catalog_and_recipe_exclude_www():
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))
    hit = [r for r in rows if str(r.get("yml", "")).endswith(".bobiverse/build-jeeves-ircd.yml")]
    assert len(hit) == 1
    text = RECIPE.read_text(encoding="utf-8")
    assert "machine: flamingo" in text
    assert "Pack-BobIrcdPayload.ps1" in text
    assert "ergo.exe" in text
    assert "jeeves-{{version}}.msi" not in text
    assert "jeeves/www" not in text
    pack = PACK.read_text(encoding="utf-8")
    assert "jeeves\\www" not in pack
    assert "must not contain www" in pack
