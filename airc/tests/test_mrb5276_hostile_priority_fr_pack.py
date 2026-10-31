"""Hostile pins for MRB #5276 (airc Priority Client FR vision pack)."""
from __future__ import annotations

import json
from pathlib import Path

from repo_layout import ROOT

FR = ROOT / "airc/docs/feature-request-airc-priority-client-2026-10-31.md"
EXAMPLE = ROOT / "airc/config/priority-instances.example.json"


def test_mrb5276_fr_pack_utf8_no_bom_and_success_rows():
    raw = FR.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    for sid in ("S1", "S2", "S3", "S4", "S5", "S6"):
        assert f"| {sid} |" in text
    assert "CredMan" in text
    assert "PRIORITY" in text
    assert "airc/VISION.md" in text
    assert "#5275" in text
    assert "See plan `drafts/backlog.md`" not in text


def test_mrb5276_example_json_no_bom_no_password():
    raw = EXAMPLE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    doc = json.loads(raw.decode("utf-8"))
    assert doc.get("instances")
    inst = doc["instances"][0]
    assert inst["id"]
    assert inst["url"].startswith("https://")
    assert inst["credentialTarget"]
    blob = raw.decode("utf-8").lower()
    assert "password" not in blob
    assert "secret" not in blob
    for key in inst:
        assert "pass" not in key.lower()
