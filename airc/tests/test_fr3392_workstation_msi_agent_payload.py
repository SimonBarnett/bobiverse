"""FR #3392: workstation profile strips MSI-laid agent briefings/skills/scripts."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
UNINSTALL = ROOT / "airc/scripts/Uninstall-Airc.ps1"
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

KEEP_SCRIPTS = (
    "Bobiverse-Common.ps1",
    "Install-Airc.ps1",
    "Uninstall-Airc.ps1",
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


def test_fr3392_common_defines_remove_helper():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Remove-BobiverseAircWorkstationAgentPayload" in t
    assert "FR #3392" in t
    for name in AGENT_SCRIPTS:
        assert name in t
    assert "AGENTS.md" in t and ".grok" in t and ".cursor" in t


def test_fr3392_install_calls_remove_when_workstation():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "Remove-BobiverseAircWorkstationAgentPayload" in t
    assert "FR #3392" in t
    assert "agent-layer skipped" in t.lower()


def test_fr3392_uninstall_purge_removes_install_log_and_system_spool():
    t = UNINSTALL.read_text(encoding="utf-8-sig")
    assert "install-airc.log" in t
    assert "systemprofile" in t.lower() or "crash-spool" in t
    assert "FR #3392" in t or "FR #3292/#3392" in t


def test_fr3392_docs_skill_describe_msi_strip():
    post = POST.read_text(encoding="utf-8")
    assert "Remove-BobiverseAircWorkstationAgentPayload" in post or "FR #3392" in post
    assert "AGENTS.md" in post and "workstation" in post.lower()
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3392" in skill or "#3392" in skill
    assert "Remove-BobiverseAircWorkstationAgentPayload" in skill


def test_fr3392_payload_stage_then_workstation_filter(tmp_path: Path):
    """Stage airc with -SkipMsi (same payload heat would ship), then apply workstation strip."""
    out = tmp_path / "pack-out"
    out.mkdir()
    # Pack writes airc-<version> under OutDir.
    pack_cmd = (
        f"& '{PACK}' -Product airc -OutDir '{out}' -SkipMsi -SkipAircExe -SkipWorkerExe "
        f"-SkipEarExe -SkipJeevesExe"
    )
    proc = _ps(pack_cmd, timeout=300)
    out_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    stages = list(out.glob("airc-*"))
    assert stages, out_text
    stage = stages[0]

    # MSI payload still contains agent layer (the bug #3392 documents).
    assert (stage / "AGENTS.md").is_file(), "stage should include AGENTS.md before strip"
    assert (stage / ".grok" / "skills").is_dir()
    assert (stage / "scripts" / "agent_control.py").is_file()
    assert (stage / "scripts" / "startworker.py").is_file()
    assert (stage / "scripts" / "grok_talk.py").is_file()

    # Apply the same strip Install-Airc runs for workstation.
    strip = (
        f". '{COMMON}'; "
        f"$r = @(Remove-BobiverseAircWorkstationAgentPayload -InstallRoot '{stage}'); "
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

    # Airc console / install tooling remains.
    for name in KEEP_SCRIPTS:
        assert (stage / "scripts" / name).is_file(), name
