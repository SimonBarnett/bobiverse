"""FR #3687: MSI AgentLayer Feature gated out for AIRC_PROFILE=client|workstation.

Agent briefings/skills/launchers must not be laid by msiexec when client/workstation
(or AIRC_AGENT_LAYER=0), even if Install-Airc.ps1 fails or is refused (PS 4.0 / #3684).
Script-side purge remains defence-in-depth only.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"

AGENT_SCRIPTS = (
    "agent_control.py",
    "startworker.py",
    "grok_talk.py",
    "Install-BootstrapTools.ps1",
    "Sync-BobiverseFromRepo.ps1",
    "Invoke-BobiverseHarvest.ps1",
)

# Client allow-list keeps intake; MSI AgentLayer must NOT claim it.
CORE_KEEP = (
    "Bobiverse-Common.ps1",
    "Install-Airc.ps1",
    "Report-BobiverseIntakeIssue.ps1",
    "airc_console_service.py",
)


def _ps(script: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
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


def test_fr3687_common_defines_msi_agent_layer_helpers():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Get-BobiverseAircMsiAgentLayerScriptNames" in t
    assert "function Test-BobiverseAircMsiAgentLayerSource" in t
    assert "function Remove-BobiverseAircMsiAgentLayerFromStage" in t
    assert "FR #3687" in t
    for name in AGENT_SCRIPTS:
        assert name in t, name
    # Intake stays on MainFeature / client allow-list (FR #3514/#3515).
    block_start = t.find("function Get-BobiverseAircMsiAgentLayerScriptNames")
    block_end = t.find("function Test-BobiverseAircMsiAgentLayerSource", block_start)
    agent_block = t[block_start:block_end]
    ret_start = agent_block.find("return @(")
    ret_end = agent_block.find(")", ret_start)
    assert "'Report-BobiverseIntakeIssue.ps1'" not in agent_block[ret_start:ret_end]
    assert "AGENTS.md" in t and ".grok" in t and ".cursor" in t


def test_fr3687_pack_wix_agent_layer_feature_condition():
    """WiX source: AgentLayerFeature Condition Level=0 for client|workstation|AGENT_LAYER=0."""
    t = PACK.read_text(encoding="utf-8-sig")
    assert "FR #3687" in t
    assert "AgentLayerFeature" in t
    assert "BobiverseAircAgentLayerFiles" in t
    assert 'Condition Level="0"' in t
    assert 'AIRC_PROFILE ~= "client"' in t
    assert 'AIRC_PROFILE ~= "workstation"' in t
    assert 'AIRC_AGENT_LAYER = "0"' in t
    assert "Test-BobiverseAircMsiAgentLayerSource" in t
    # Split only for airc product.
    assert "$Name -eq 'airc'" in t


def test_fr3687_classifier_pins_agent_vs_core():
    # One assertion per Source to keep PS argv simple on Windows.
    cases = [
        (r"$(var.StageDir)\AGENTS.md", True),
        (r"$(var.StageDir)\CLAUDE.md", True),
        (r"$(var.StageDir)\GROK.md", True),
        (r"$(var.StageDir)\.grok\skills\x\SKILL.md", True),
        (r"$(var.StageDir)\.cursor\rules\bob.mdc", True),
        (r"$(var.StageDir)\scripts\agent_control.py", True),
        (r"$(var.StageDir)\scripts\startworker.py", True),
        (r"$(var.StageDir)\scripts\Report-BobiverseIntakeIssue.ps1", False),
        (r"$(var.StageDir)\scripts\Install-Airc.ps1", False),
        (r"$(var.StageDir)\scripts\Bobiverse-Common.ps1", False),
        (r"$(var.StageDir)\airc\airc.exe", False),
    ]
    for src, want in cases:
        script = (
            f". '{COMMON}'; "
            f"$got = [bool](Test-BobiverseAircMsiAgentLayerSource -Source '{src}'); "
            f"if ($got -ne ${str(want).lower()}) {{ "
            f"Write-Output \"FAIL src=$src got=$got want={want}\"; exit 1 "
            f"}} else {{ 'ok' }}"
        )
        proc = _ps(script, timeout=60)
        assert proc.returncode == 0, (src, proc.stdout or "", proc.stderr or "")
        assert "ok" in (proc.stdout or ""), src


def test_fr3687_heat_component_split_moves_agent_files(tmp_path: Path):
    """Synthetic heat XML: agent File Components move to BobiverseAircAgentLayerFiles."""
    harvested = tmp_path / "HarvestedFiles.wxs"
    harvested.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Fragment>
    <ComponentGroup Id="BobiverseaircFiles">
      <Component Id="cmpAgents" Directory="INSTALLDIR" Guid="*">
        <File Id="filAgents" KeyPath="yes" Source="$(var.StageDir)\\AGENTS.md" />
      </Component>
      <Component Id="cmpGrokSkill" Directory="dirGrok" Guid="*">
        <File Id="filSkill" KeyPath="yes" Source="$(var.StageDir)\\.grok\\skills\\x\\SKILL.md" />
      </Component>
      <Component Id="cmpAgentCtl" Directory="dirScripts" Guid="*">
        <File Id="filAgentCtl" KeyPath="yes" Source="$(var.StageDir)\\scripts\\agent_control.py" />
      </Component>
      <Component Id="cmpIntake" Directory="dirScripts" Guid="*">
        <File Id="filIntake" KeyPath="yes" Source="$(var.StageDir)\\scripts\\Report-BobiverseIntakeIssue.ps1" />
      </Component>
      <Component Id="cmpInstall" Directory="dirScripts" Guid="*">
        <File Id="filInstall" KeyPath="yes" Source="$(var.StageDir)\\scripts\\Install-Airc.ps1" />
      </Component>
      <Component Id="cmpNssm" Directory="dirNssm" Guid="*">
        <File Id="filNssm" KeyPath="yes" Source="$(var.StageDir)\\third_party\\nssm\\win64\\nssm.exe" />
      </Component>
    </ComponentGroup>
  </Fragment>
</Wix>
""",
        encoding="utf-8",
    )
    out_json = tmp_path / "split.json"
    script = (
        f". '{COMMON}'; "
        f"$harvested = '{harvested}'; "
        "$cg = 'BobiverseaircFiles'; "
        "$agentCg = 'BobiverseAircAgentLayerFiles'; "
        "[xml]$hx = Get-Content -LiteralPath $harvested -Raw -Encoding UTF8; "
        "$wns = New-Object System.Xml.XmlNamespaceManager($hx.NameTable); "
        "$wns.AddNamespace('w', 'http://schemas.microsoft.com/wix/2006/wi'); "
        "$mainGroup = $hx.SelectSingleNode(\"//w:ComponentGroup[@Id='$cg']\", $wns); "
        "$agentGroup = $hx.CreateElement('ComponentGroup', $mainGroup.NamespaceURI); "
        "$agentGroup.SetAttribute('Id', $agentCg); "
        "$toMove = New-Object System.Collections.Generic.List[System.Xml.XmlElement]; "
        "foreach ($comp in @($mainGroup.SelectNodes('w:Component', $wns))) { "
        "  $isAgent = $false; "
        "  foreach ($f in @($comp.SelectNodes('w:File', $wns))) { "
        "    if (Test-BobiverseAircMsiAgentLayerSource -Source ([string]$f.GetAttribute('Source'))) { "
        "      $isAgent = $true; break "
        "    } "
        "  }; "
        "  if ($isAgent) { [void]$toMove.Add($comp) } "
        "}; "
        "foreach ($comp in $toMove) { "
        "  [void]$mainGroup.RemoveChild($comp); "
        "  [void]$agentGroup.AppendChild($comp) "
        "}; "
        "[void]$mainGroup.ParentNode.AppendChild($agentGroup); "
        "$hx.Save($harvested); "
        "$mainIds = @($mainGroup.SelectNodes('w:Component', $wns) | ForEach-Object { $_.GetAttribute('Id') }); "
        "$agentIds = @($agentGroup.SelectNodes('w:Component', $wns) | ForEach-Object { $_.GetAttribute('Id') }); "
        "@{ moved=$toMove.Count; main=$mainIds; agent=$agentIds } | ConvertTo-Json -Compress | "
        f"Set-Content -LiteralPath '{out_json}' -Encoding utf8"
    )
    proc = _ps(script, timeout=60)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    import json

    data = json.loads(out_json.read_text(encoding="utf-8-sig"))
    assert data["moved"] == 3, data
    assert set(data["agent"]) == {"cmpAgents", "cmpGrokSkill", "cmpAgentCtl"}
    assert set(data["main"]) == {"cmpIntake", "cmpInstall", "cmpNssm"}


def test_fr3687_stage_strip_without_install_airc(tmp_path: Path):
    """Apply MSI agent-layer exclusion to a staged tree without Install-Airc.ps1."""
    out = tmp_path / "pack-out"
    out.mkdir()
    pack_cmd = (
        f"& '{PACK}' -Product airc -OutDir '{out}' -SkipMsi -SkipAircExe -SkipWorkerExe "
        f"-SkipEarExe -SkipJeevesExe"
    )
    proc = _ps(pack_cmd, timeout=300)
    out_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    stages = list(out.glob("airc-*"))
    assert stages, out_text
    stage = stages[0]

    assert (stage / "AGENTS.md").is_file(), "stage still includes agent layer before MSI Feature gate"
    assert (stage / ".grok" / "skills").is_dir()
    assert (stage / "scripts" / "agent_control.py").is_file()
    assert (stage / "scripts" / "Report-BobiverseIntakeIssue.ps1").is_file()

    strip = (
        f". '{COMMON}'; "
        f"$r = @(Remove-BobiverseAircMsiAgentLayerFromStage -InstallRoot '{stage}'); "
        f"$r | ConvertTo-Json -Compress"
    )
    proc2 = _ps(strip, timeout=60)
    assert proc2.returncode == 0, (proc2.stdout or "") + (proc2.stderr or "")

    assert not (stage / "AGENTS.md").exists()
    assert not (stage / "CLAUDE.md").exists()
    assert not (stage / "GROK.md").exists()
    assert not (stage / ".cursor").exists()
    assert not (stage / ".grok").exists()
    for name in AGENT_SCRIPTS:
        assert not (stage / "scripts" / name).exists(), name

    for name in CORE_KEEP:
        assert (stage / "scripts" / name).is_file(), name


def test_fr3687_docs_skill_describe_msi_feature_gate():
    post = POST.read_text(encoding="utf-8")
    assert "FR #3687" in post
    assert "AgentLayerFeature" in post or "BobiverseAircAgentLayerFiles" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3687" in skill or "#3687" in skill
    assert "AgentLayerFeature" in skill or "BobiverseAircAgentLayerFiles" in skill
