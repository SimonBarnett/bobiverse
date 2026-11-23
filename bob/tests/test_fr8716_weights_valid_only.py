"""FR #8716 / BOB-14: Weights dropdowns ⊆ webhook clis catalog; invalid options absent."""
from __future__ import annotations

import json
from pathlib import Path

import models_catalog as mc
from bobcallback import handle_request
from repo_layout import REPO

WEIGHTS = REPO / "bob" / "tray" / "dialogs" / "WeightsForm.cs"
CLIENT = REPO / "bob" / "tray" / "dialogs" / "BobModelsClient.cs"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"

FIXTURE = {
    "version": 1,
    "clis": {
        "grok": [
            {
                "model": "fixture-grok-a",
                "contexts": ["256", "500"],
                "efforts": ["low", "medium", "high"],
            }
        ],
        "cursor": [
            {
                "model": "fixture-cursor-a",
                "contexts": [],
                "efforts": [],
            }
        ],
        "opencode": [
            {
                "model": "fixture-oc-a",
                "contexts": [],
                "efforts": [],
            }
        ],
    },
}


def test_source_pins_valid_only_dropdowns():
    w = WEIGHTS.read_text(encoding="utf-8-sig")
    c = CLIENT.read_text(encoding="utf-8-sig")
    t = TRAY.read_text(encoding="utf-8-sig")
    assert "FR #8716" in w
    assert "EditingControlShowing" in w
    assert "DumpValidOptions" in w
    assert '"256"' not in w and '"512"' not in w and '"med"' not in w
    assert "ParseClis" in c
    assert "ModelsForCli" in c
    assert "--dump-weights-valid" in t


def test_get_models_includes_clis_allow_list(tmp_path: Path):
    mc.ensure_valid_combos_seeded(tmp_path)
    # Overwrite with fixture so the assertion is deterministic.
    (tmp_path / mc.MODELS_VALID_COMBOS_NAME).write_text(
        json.dumps(FIXTURE), encoding="utf-8"
    )
    code, body = handle_request(
        "GET",
        mc.MODELS_PATH,
        {},
        b"",
        "127.0.0.1",
        tmp_path,
        allow_ips={"127.0.0.1"},
    )
    assert code == 200
    doc = json.loads(body.decode("utf-8"))
    assert "agents" in doc
    assert "clis" in doc
    # FR #8819 nested Si shape (DisplayCli keys + models/contexts/efforts).
    assert set(doc["clis"]) == {"Grok", "Cursor", "Opencode"}
    assert "fixture-grok-a" in doc["clis"]["Grok"]["models"]
    assert "256" in doc["clis"]["Grok"]["models"]["fixture-grok-a"]["contexts"]
    assert "500" in doc["clis"]["Grok"]["models"]["fixture-grok-a"]["contexts"]
    # FR #9258: Cursor/OpenCode models present with empty contexts (no offer).
    assert doc["clis"]["Cursor"]["models"]["fixture-cursor-a"]["contexts"] == {}
    blob = json.dumps(doc["clis"])
    assert '"128k"' not in blob
    assert '"med"' not in blob


def test_valid_combos_public_doc_shape():
    cat = mc.valid_combos_public_doc(
        mc.ValidCombosCatalog(
            available=True,
            version=1,
            clis={
                "grok": [
                    mc.ModelComboRow(
                        model="fixture-grok-a",
                        contexts=["256", "500"],
                        efforts=["low", "medium", "high"],
                    )
                ]
            },
        )
    )
    assert "grok" in cat
    assert cat["grok"][0]["model"] == "fixture-grok-a"
    assert "256" in cat["grok"][0]["contexts"]
    assert "high" in cat["grok"][0]["efforts"]
