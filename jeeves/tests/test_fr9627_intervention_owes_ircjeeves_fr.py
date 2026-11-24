# -*- coding: utf-8 -*-
"""FR #9627: CAST IRON — every MONITORING intervention owes an ircJeeves FR.

Pins the rule in owning books and the harvest checklist gate that fails
intervention Summary/Lesson text without a linked product FR number.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from repo_layout import REPO

JEEVES = REPO / "jeeves"
AGENTS = JEEVES / "AGENTS.md"
MONITOR = JEEVES / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
MONITOR_START = JEEVES / ".grok" / "skills" / "monitor-start" / "SKILL.md"
HARVEST = REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
GATE = JEEVES / "tools" / "monitor" / "intervention_fr_gate.py"
HARVEST_PS1 = REPO / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
VISION = JEEVES / "VISION.md"


def _load_gate():
    spec = importlib.util.spec_from_file_location("intervention_fr_gate", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_fr9627_agents_and_skills_state_cast_iron():
    for path in (AGENTS, MONITOR, MONITOR_START, HARVEST):
        assert path.is_file(), path
        text = path.read_text(encoding="utf-8-sig")
        assert "9627" in text, f"FR #9627 missing from {path}"
        assert "ircJeeves" in text or "ircjeeves" in text.lower(), path
        low = text.lower()
        assert "intervention" in low or "!assign" in low, path
        assert "determinist" in low or "bridge" in low, path


def test_fr9627_gate_module_exists():
    assert GATE.is_file()
    raw = GATE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "gate must be UTF-8 without BOM"


def test_fr9627_intervention_without_fr_fails():
    g = _load_gate()
    err = g.check_intervention_harvest(
        "MONITORING ran !assign flamingo-1 to unblock idle seat",
        "LLM bridge kept the queue moving",
    )
    assert err is not None
    assert "9627" in err


def test_fr9627_intervention_with_product_fr_passes():
    g = _load_gate()
    assert (
        g.check_intervention_harvest(
            "MONITORING !assign bridge for idle+offerable",
            "Same-turn product FR #9628 for offer_to_idle; FR #8827 is bridge-only",
        )
        is None
    )
    assert (
        g.check_intervention_harvest(
            "cleared giveup via !cleargiveup",
            "filed SimonBarnett/bobiverse#9633",
        )
        is None
    )


def test_fr9627_non_intervention_harvest_passes():
    g = _load_gate()
    assert (
        g.check_intervention_harvest(
            "MRB #9610 PASS: seat-silent-end key by machine",
            "Seat-end intake class keys omit nick",
        )
        is None
    )


def test_fr9627_cli_exit_codes():
    g = _load_gate()
    assert g.main(["--summary", "routine harvest", "--lesson", "no bridge"]) == 0
    assert (
        g.main(
            [
                "--summary",
                "ran !sweep to clear stuck",
                "--lesson",
                "ops unblock without filing",
            ]
        )
        == 1
    )
    assert (
        g.main(
            [
                "--summary",
                "ran !sweep to clear stuck",
                "--lesson",
                "product FR #8377 regression",
            ]
        )
        == 0
    )


def test_fr9627_harvest_ps1_wires_gate():
    text = HARVEST_PS1.read_text(encoding="utf-8-sig")
    assert "9627" in text
    assert "Test-HarvestInterventionMissingFr" in text or "intervention_fr_gate" in text


def test_fr9627_vision_monitoring_cites_rule():
    text = VISION.read_text(encoding="utf-8-sig")
    assert "9627" in text
    assert "8827" in text
