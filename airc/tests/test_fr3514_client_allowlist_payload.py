"""FR #3514: AIRC_PROFILE=client keep-only tree (allow-list, not workstation deny-list)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"

# Must survive client allow-list (install/uninstall/runtime + crash intake).
KEEP_SCRIPTS = (
    "Bobiverse-Common.ps1",
    "Install-Airc.ps1",
    "Install-AircConsole.ps1",
    "Uninstall-Airc.ps1",
    "Recover-BobiverseService.ps1",
    "Resolve-AircConsoleNssm.ps1",
    "Start-AircConsole.ps1",
    "Report-BobiverseIntakeIssue.ps1",
    "airc_console_service.py",
    "crash_report.py",
)

# Must be gone after client allow-list (union leftovers / docs).
GONE_SCRIPTS = (
    "jeeves_main.py",
    "gitclaim.py",
    "shop_listen.py",
    "bob_worker.py",
    "Install-Jeeves.ps1",
    "Install-Bob.ps1",
    "agent_control.py",
    "startworker.py",
    "Invoke-BobiverseHarvest.ps1",
    "Sync-BobiverseFromRepo.ps1",
)


def _ps(script: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
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


def test_fr3514_common_defines_client_allowlist_helpers():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Remove-BobiverseAircClientExtraPayload" in t
    assert "function Get-BobiverseAircClientAllowedScriptNames" in t
    assert "FR #3514" in t
    for name in KEEP_SCRIPTS:
        assert name in t, name
    # Deny-list workstation helper remains for non-client.
    assert "function Remove-BobiverseAircWorkstationAgentPayload" in t


def test_fr3514_install_uses_client_allowlist_not_only_deny():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "Remove-BobiverseAircClientExtraPayload" in t
    assert "FR #3514" in t
    assert "prof -eq 'client'" in t
    # Workstation path still uses deny-list strip.
    assert "Remove-BobiverseAircWorkstationAgentPayload" in t


def test_fr3514_docs_skill_describe_client_allowlist():
    post = POST.read_text(encoding="utf-8")
    assert "FR #3514" in post
    assert "Remove-BobiverseAircClientExtraPayload" in post or "allow-list" in post.lower()
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3514" in skill
    assert "allow-list" in skill.lower() or "allowlist" in skill.lower() or "ClientExtra" in skill


def test_fr3514_pack_then_client_allowlist_tree(tmp_path: Path):
    """Stage MSI payload, apply client allow-list; assert no Jeeves/Bob/docs leftovers."""
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

    # Precondition: union payload still has foreign product scripts + docs.
    assert (stage / "docs").is_dir(), "stage should include docs before client purge"
    assert (stage / "scripts" / "Install-Jeeves.ps1").is_file() or (
        stage / "scripts" / "jeeves_main.py"
    ).is_file(), "stage should include Jeeves leftovers before purge"

    strip = (
        f". '{COMMON}'; "
        f"$r = @(Remove-BobiverseAircClientExtraPayload -InstallRoot '{stage}'); "
        f"Write-Output ('removed=' + $r.Count); "
        f"$scripts = @(Get-ChildItem -LiteralPath (Join-Path '{stage}' 'scripts') -File "
        f"| Select-Object -ExpandProperty Name); "
        f"Write-Output ('script_count=' + $scripts.Count); "
        f"$scripts | Sort-Object | ForEach-Object {{ Write-Output ('script:' + $_) }}"
    )
    proc2 = _ps(strip, timeout=120)
    text2 = (proc2.stdout or "") + "\n" + (proc2.stderr or "")
    assert proc2.returncode == 0, text2

    # Top-level keep / drop.
    assert (stage / "VERSION").is_file()
    assert (stage / "BUILD.json").is_file()
    assert (stage / "config").is_dir()
    assert (stage / "scripts").is_dir()
    assert (stage / "third_party" / "nssm").is_dir()
    assert not (stage / "docs").exists()
    assert not (stage / "src").exists()
    assert not (stage / "assets").exists()
    assert not (stage / "AGENTS.md").exists()
    assert not (stage / ".grok").exists()
    assert not (stage / ".cursor").exists()

    for name in KEEP_SCRIPTS:
        assert (stage / "scripts" / name).is_file(), f"missing keep {name}\n{text2}"

    for name in GONE_SCRIPTS:
        assert not (stage / "scripts" / name).exists(), f"still present {name}"

    # Allow-list size: only the named install/runtime set (no 45+ py / 69+ ps1).
    script_files = list((stage / "scripts").glob("*"))
    assert len(script_files) <= 25, (
        f"client scripts still too many ({len(script_files)}): "
        + ", ".join(sorted(p.name for p in script_files))
    )
    assert "script_count=" in text2
