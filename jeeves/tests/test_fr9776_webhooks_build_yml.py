"""FR #9776: !build recipe packs the webhooks site kit only."""
from __future__ import annotations

import json

from repo_layout import ROOT

RECIPE = ROOT / ".bobiverse" / "build-webhooks.yml"
CATALOG = ROOT / "common" / "defaults" / "builds-catalog.example.json"


def test_fr9776_catalog_points_at_webhooks_recipe():
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))
    hit = [r for r in rows if r.get("yml", "").endswith(".bobiverse/build-webhooks.yml")]
    assert len(hit) == 1
    assert hit[0]["install"] == "flamingo"
    text = RECIPE.read_text(encoding="utf-8")
    assert "machine: flamingo" in text
    assert "Pack-BobWebhooksSiteKit.ps1" in text
    assert "jeeves-{{version}}.msi" not in text
    assert "ergo.exe" not in text
    assert "MANIFEST.json" in text
