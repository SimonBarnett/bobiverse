"""MRB #3695 hostile pins for FR #3687 MSI AgentLayerFeature.

Pins that survive on main after product merge:
- Pack WiX AgentLayerFeature Condition Level=0 for client|workstation|AIRC_AGENT_LAYER=0
- Classifier omits Report-BobiverseIntakeIssue.ps1 (MainFeature / client allow-list)
- Common helpers + FR #3687 markers contiguous
- Docs/skill name the Feature gate
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def test_mrb3695_pack_agent_layer_feature_condition_contiguous():
    t = PACK.read_text(encoding="utf-8-sig")
    assert "FR #3687" in t
    assert "FR #3740" in t
    assert 'Feature Id="AgentLayerFeature"' in t
    assert "BobiverseAircAgentLayerFiles" in t
    needle = (
        'Condition Level="0"><![CDATA[AIRC_PROFILE ~= "client" OR '
        'AIRC_PROFILE ~= "workstation" OR AIRC_AGENT_LAYER = "0"]]></Condition>'
    )
    assert needle in t
    assert "Move-BobiverseAircMsiAgentLayerComponents" in t
    assert "-FailIfNone" in t
    # airc-only split
    assert "$Name -eq 'airc'" in t


def test_mrb3695_intake_not_in_agent_script_list():
    t = COMMON.read_text(encoding="utf-8-sig")
    start = t.find("function Get-BobiverseAircMsiAgentLayerScriptNames")
    end = t.find("function Test-BobiverseAircMsiAgentLayerSource", start)
    assert start >= 0 and end > start
    block = t[start:end]
    ret = block.find("return @(")
    close = block.find(")", ret)
    names = block[ret:close]
    assert "Report-BobiverseIntakeIssue.ps1" not in names
    assert "agent_control.py" in names
    assert "Install-BootstrapTools.ps1" in names


def test_mrb3695_common_helpers_and_ascii():
    raw = COMMON.read_bytes()
    assert b"\xef\xbb\xbf" not in raw[:3]
    text = raw.decode("utf-8")
    assert all(ord(c) < 128 for c in text), "Bobiverse-Common.ps1 must stay ASCII for WinPS"
    assert "function Test-BobiverseAircMsiAgentLayerSource" in text
    assert "function Remove-BobiverseAircMsiAgentLayerFromStage" in text
    assert "function Move-BobiverseAircMsiAgentLayerComponents" in text
    assert "FR #3687" in text
    assert "FR #3740" in text


def test_mrb3695_docs_skill_feature_gate():
    post = POST.read_text(encoding="utf-8")
    assert "FR #3687" in post
    assert "AgentLayerFeature" in post or "BobiverseAircAgentLayerFiles" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3687" in skill
    assert "AgentLayerFeature" in skill or "BobiverseAircAgentLayerFiles" in skill
