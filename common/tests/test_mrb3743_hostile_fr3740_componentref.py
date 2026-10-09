"""MRB #3743 hostile pins for FR #3740 AgentLayerFeature ComponentRef move.

Product merge: PR #3743. Pins that must survive on main:
- heat shape: Components under DirectoryRef, ComponentRef under group
- Move-BobiverseAircMsiAgentLayerComponents retargets refs; FailIfNone
- Pack airc path calls Move with -FailIfNone
- legacy under-group Component select moves 0 on heat shape
- docs/skill name ComponentRef + fail-closed
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
PRODUCT = ROOT / "airc/tests/test_fr3687_msi_agent_layer_feature.py"


def _ps(script: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(ROOT),
    )


def test_mrb3743_pack_calls_move_fail_closed():
    t = PACK.read_text(encoding="utf-8-sig")
    assert "Move-BobiverseAircMsiAgentLayerComponents" in t
    assert "-FailIfNone" in t
    assert "FR #3740" in t
    assert "$Name -eq 'airc'" in t
    # Must not keep the broken under-group-only Component loop as the sole mover.
    i = t.find("Move-BobiverseAircMsiAgentLayerComponents")
    assert i >= 0
    window = t[max(0, i - 200) : i + 200]
    assert "FailIfNone" in window or "-FailIfNone" in t


def test_mrb3743_helper_and_product_tests_present():
    c = COMMON.read_text(encoding="utf-8-sig")
    assert "function Move-BobiverseAircMsiAgentLayerComponents" in c
    assert "FailIfNone" in c
    assert "ComponentRef" in c
    assert "FR #3740" in c
    p = PRODUCT.read_text(encoding="utf-8")
    assert "test_fr3740_heat_componentref_split_moves_agent_files" in p
    assert "test_fr3740_fail_closed_when_zero_agent_components" in p
    assert "legacyUnderGroup" in p


def test_mrb3743_heat_componentref_move_behaviour(tmp_path: Path):
    """Hostile: heat-shaped harvest must move ComponentRefs; legacy Component count=0."""
    harvested = tmp_path / "HarvestedFiles.wxs"
    harvested.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Fragment>
    <DirectoryRef Id="INSTALLDIR">
      <Component Id="cmpAgents" Guid="*">
        <File Id="filAgents" KeyPath="yes" Source="$(var.StageDir)\\AGENTS.md" />
      </Component>
      <Component Id="cmpInstall" Guid="*">
        <File Id="filInstall" KeyPath="yes" Source="$(var.StageDir)\\scripts\\Install-Airc.ps1" />
      </Component>
    </DirectoryRef>
  </Fragment>
  <Fragment>
    <ComponentGroup Id="BobiverseaircFiles">
      <ComponentRef Id="cmpAgents" />
      <ComponentRef Id="cmpInstall" />
    </ComponentGroup>
  </Fragment>
</Wix>
""",
        encoding="utf-8",
    )
    out_json = tmp_path / "out.json"
    script = (
        f". '{COMMON}'; "
        f"$harvested = '{harvested}'; "
        "[xml]$hx = Get-Content -LiteralPath $harvested -Raw -Encoding UTF8; "
        "$wns = New-Object System.Xml.XmlNamespaceManager($hx.NameTable); "
        "$wns.AddNamespace('w', 'http://schemas.microsoft.com/wix/2006/wi'); "
        "$mainGroup = $hx.SelectSingleNode(\"//w:ComponentGroup[@Id='BobiverseaircFiles']\", $wns); "
        "$legacy = @($mainGroup.SelectNodes('w:Component', $wns)).Count; "
        "$moved = Move-BobiverseAircMsiAgentLayerComponents -HarvestXml $hx -NamespaceManager $wns "
        "-MainGroupId 'BobiverseaircFiles' -AgentGroupId 'BobiverseAircAgentLayerFiles' -FailIfNone; "
        "$agentGroup = $hx.SelectSingleNode(\"//w:ComponentGroup[@Id='BobiverseAircAgentLayerFiles']\", $wns); "
        "$agentRefs = @($agentGroup.SelectNodes('w:ComponentRef', $wns) | ForEach-Object { $_.GetAttribute('Id') }); "
        "$mainRefs = @($mainGroup.SelectNodes('w:ComponentRef', $wns) | ForEach-Object { $_.GetAttribute('Id') }); "
        "@{ legacy=$legacy; moved=$moved; agent=$agentRefs; main=$mainRefs } | ConvertTo-Json -Compress | "
        f"Set-Content -LiteralPath '{out_json}' -Encoding utf8"
    )
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    data = json.loads(out_json.read_text(encoding="utf-8-sig"))
    assert data["legacy"] == 0, data
    assert data["moved"] == 1, data
    assert data["agent"] == ["cmpAgents"], data
    assert data["main"] == ["cmpInstall"], data


def test_mrb3743_docs_skill_componentref_fail_closed():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3740" in skill or "#3740" in skill
    assert "ComponentRef" in skill
    assert "fail" in skill.lower() and "closed" in skill.lower()
    # Contiguous playbook window around the FR cite (ComponentRef + fail-closed follow).
    i = skill.find("#3740")
    assert i >= 0
    window = skill[max(0, i - 40) : i + 420]
    assert "ComponentRef" in window
    assert "fail" in window.lower() and "closed" in window.lower()
    post = POST.read_text(encoding="utf-8")
    assert "FR #3740" in post or "#3740" in post
    assert "ComponentRef" in post
    assert "Move-BobiverseAircMsiAgentLayerComponents" in post
