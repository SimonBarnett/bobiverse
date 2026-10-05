"""Audit source completeness for every executable built or shipped by bobiverse.

The release builders are PowerShell rather than checked-in PyInstaller specs: these
fixtures mirror their explicit source arguments and packaged source trees. Keeping
the manifest here makes a missing/locally-only build input fail in CI before an MSI
can be produced from a developer checkout.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import REPO, resolve


# Paths are the names consumed by Get-BobiverseRepoPath / the flat pack layout.
EXE_INPUTS: dict[str, tuple[str, ...]] = {
    "bob-worker.exe": (
        "bob/scripts/Build-BobWorker.ps1",
        "bob/scripts/bob_worker.py",
        "common/scripts/crash_report.py",
        "third_party/bob-tray/assets/bob-systray.ico",
    ),
    "bob-ear.exe": (
        "bob/scripts/Build-BobEar.ps1",
        "scripts/irc_agent.py",
        "common/scripts/crash_report.py",
        "third_party/bob-tray/assets/bob-systray.ico",
    ),
    "Watch-AgentHealth.exe": (
        "bob/scripts/Build-BobWatcher.ps1",
        "bob/agentwatcher/watch_agent_health.py",
        "bob/agentwatcher/Watch-AgentHealth.ps1",
        "common/scripts/crash_report.py",
    ),
    "jeeves.exe": (
        "jeeves/scripts/Build-Jeeves.ps1",
        "scripts/jeeves_main.py",
        "common/scripts/crash_report.py",
    ),
    "airc.exe": (
        "airc/scripts/Build-Airc.ps1",
        "airc/scripts/airc_console_service.py",
        "common/scripts/crash_report.py",
    ),
    "bob-about.exe": (
        "bob/scripts/Build-BobDialogs.ps1",
        "third_party/bob-tray/dialogs/BobDialogsCommon.cs",
        "third_party/bob-tray/dialogs/BobAbout.cs",
        "third_party/bob-tray/dialogs/CrashHook.cs",
        "third_party/bob-tray/dialogs/bob-dialogs.manifest",
        "third_party/bob-tray/assets/bob-systray.ico",
        "third_party/bob-tray/assets/ntsa-gut-logo.png",
    ),
    "bob-status.exe": (
        "bob/scripts/Build-BobDialogs.ps1",
        "third_party/bob-tray/dialogs/BobDialogsCommon.cs",
        "third_party/bob-tray/dialogs/BobStatus.cs",
        "third_party/bob-tray/dialogs/CrashHook.cs",
        "third_party/bob-tray/dialogs/bob-dialogs.manifest",
        "third_party/bob-tray/assets/bob-systray.ico",
        "third_party/bob-tray/assets/ntsa-gut-logo.png",
    ),
    "bob-tray.exe": (
        "bob/scripts/Build-BobDialogs.ps1",
        "third_party/bob-tray/dialogs/BobDialogsCommon.cs",
        "third_party/bob-tray/dialogs/BobAbout.cs",
        "third_party/bob-tray/dialogs/BobStatus.cs",
        "third_party/bob-tray/dialogs/BobTray.cs",
        "third_party/bob-tray/dialogs/CrashHook.cs",
        "third_party/bob-tray/dialogs/bob-dialogs.manifest",
        "third_party/bob-tray/assets/bob-systray.ico",
        "third_party/bob-tray/assets/ntsa-gut-logo.png",
    ),
}

# Pack-BobiverseRelease copies these trees into the MSI and the PyInstaller
# scripts put every scripts directory on sys.path. Any new source there must be
# committed, not merely present on the build machine.
BUILD_SOURCE_ROOTS = (
    "common/scripts",
    "jeeves/scripts",
    "bob/scripts",
    "airc/scripts",
    "bob/agentwatcher",
    "bob/tray",
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=False, capture_output=True, text=True
    )


def _real(rel: str) -> Path:
    return resolve(rel)


def _tracked_at_head(rel: str) -> bool:
    p = _git("ls-tree", "--name-only", "HEAD", "--", rel.replace("\\", "/"))
    return p.returncode == 0 and bool(p.stdout.strip())


def _status_paths() -> set[str]:
    p = _git("status", "--porcelain=v1", "--untracked-files=all")
    assert p.returncode == 0, p.stderr
    return {
        line[3:].replace("\\", "/")
        for line in p.stdout.splitlines()
        if len(line) >= 4 and line[0:2] != "!!"
    }


def test_every_shipped_exe_has_committed_build_inputs():
    missing: list[str] = []
    for exe, inputs in EXE_INPUTS.items():
        for rel in inputs:
            path = _real(rel)
            git_rel = path.relative_to(REPO).as_posix()
            if not path.is_file():
                missing.append(f"{exe}: filesystem missing {rel} -> {git_rel}")
            elif not _tracked_at_head(git_rel):
                missing.append(f"{exe}: not committed at HEAD {git_rel}")
    assert not missing, "\n".join(missing)


def test_no_build_source_tree_is_untracked():
    dirty = _status_paths()
    offenders: list[str] = []
    for root in BUILD_SOURCE_ROOTS:
        base = _real(root)
        if not base.is_dir():
            continue
        prefix = base.relative_to(REPO).as_posix().rstrip("/") + "/"
        for rel in sorted(dirty):
            if rel == prefix.rstrip("/") or rel.startswith(prefix):
                offenders.append(f"{root}: {rel}")
    assert not offenders, "untracked/uncommitted build input(s):\n" + "\n".join(offenders)


def test_build_scripts_and_pack_manifest_cover_the_executables():
    pack = _real("common/scripts/Pack-BobiverseRelease.ps1").read_text(encoding="utf-8-sig")
    for exe, inputs in EXE_INPUTS.items():
        builder = _real(inputs[0]).read_text(encoding="utf-8-sig")
        assert exe in builder, f"{inputs[0]} does not name {exe}"
        assert exe in pack or exe == "bob-tray.exe", f"pack does not mention {exe}"
    assert "Build-BobWorker.ps1" in pack
    assert "Build-BobEar.ps1" in pack
    assert "Build-BobWatcher.ps1" in pack
    assert "Build-BobDialogs.ps1" in pack
