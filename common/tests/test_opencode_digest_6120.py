"""Digest / webhook tests for OpenCode fuel ids (issue #6120)."""
from __future__ import annotations

from pathlib import Path

import bobreport


def test_pcent_retains_opencode_fuel_ids(tmp_path: Path):
    raw = {
        "online": True,
        "pcent": {
            "cursor-models": 40,
            "opencode-free": 100,
            "opencode-go": 50,
        },
    }
    ent = bobreport._coerce_machine("marchhare", raw)
    assert ent["pcent"]["opencode-free"] == 100
    assert ent["pcent"]["opencode-go"] == 50


def test_export_machine_for_tray_keeps_opencode_pcent(tmp_path: Path):
    home = tmp_path / "digest"
    home.mkdir()
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "online": True,
        "pcent": {"opencode-free": 100, "opencode-go": 50},
    }
    bobreport.save_digest(home, doc)
    exported = bobreport.export_machine_for_tray(home, "marchhare", doc["machines"]["marchhare"])
    assert exported["pcent"]["opencode-free"] == 100
    assert exported["pcent"]["opencode-go"] == 50
