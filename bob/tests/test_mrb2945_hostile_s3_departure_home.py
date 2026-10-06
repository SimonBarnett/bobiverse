"""Hostile pins for MRB #2945: S3 departure home playbook in bob troubleshooting.

Harvest tip wrongly parked the lesson under harvest/SKILL.md; MRB moved it to
bobiverse-bob-troubleshooting (product home). Product fix remains FR #2943.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def test_mrb2945_troubleshooting_pins_s3_departure_home():
    text = SKILL.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.startswith("\ufeff")
    assert "FR #2943" in text
    assert "InstallRoot\\home" in text or "InstallRoot\\home" in text.replace("/", "\\")
    assert "USERPROFILE" in text or ".bobiverse" in text
    assert "ForceNew" in text
    assert "Restart-BobEar" in text
    assert "undrained" in text.lower() or "never reached the ear" in text


def test_mrb2945_harvest_does_not_hold_s3_departure_bullet():
    text = HARVEST.read_text(encoding="utf-8")
    assert "UAT S3: TipForm ForceNew and Restart-BobEar must write departure" not in text
