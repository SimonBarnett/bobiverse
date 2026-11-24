"""FR #9800: .NET 8 bob-worker-net project + build CI pins.

Pins: SDK-style net8.0 project, Build-BobWorkerNet.ps1 invokes dotnet (never csc),
build-bob-worker-net.yml uses setup-dotnet, docs state airc no-SDK does not apply,
--version / crash hook surface in Program.cs.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-worker-net.yml"
BUILD = ROOT / "bob" / "scripts" / "Build-BobWorkerNet.ps1"
CSPROJ = ROOT / "bob" / "worker" / "dotnet" / "BobWorkerNet.csproj"
PROGRAM = ROOT / "bob" / "worker" / "dotnet" / "Program.cs"
GEN = ROOT / "bob" / "worker" / "dotnet" / "GeneratedSourceCommit.cs"
DOCS = ROOT / "bob" / "docs" / "bob-worker-net.md"


def _t(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fr9800_project_is_net8_sdk_style():
    assert CSPROJ.is_file(), "missing bob/worker/dotnet/BobWorkerNet.csproj"
    text = _t(CSPROJ)
    assert 'Sdk="Microsoft.NET.Sdk"' in text
    assert "<TargetFramework>net8.0</TargetFramework>" in text
    assert "<PublishSingleFile>true</PublishSingleFile>" in text
    assert "<SelfContained>true</SelfContained>" in text
    assert "<RuntimeIdentifier>win-x64</RuntimeIdentifier>" in text
    assert "<AssemblyName>bob-worker-net</AssemblyName>" in text
    assert "no-SDK" in text or "Framework 4" in text


def test_fr9800_program_version_and_crash_hook():
    assert PROGRAM.is_file()
    text = _t(PROGRAM)
    assert "--version" in text
    assert "return 0" in text
    assert "InstallCrashHook" in text
    assert "UnhandledException" in text
    assert "bob-worker-net-crash.txt" in text
    assert "BOB_WORKER_RUN_DIR" in text
    assert "return 64" in text
    assert GEN.is_file()
    assert "GeneratedSourceCommit" in _t(GEN)


def test_fr9800_build_script_invokes_dotnet_not_csc():
    assert BUILD.is_file(), "missing bob/scripts/Build-BobWorkerNet.ps1"
    text = _t(BUILD)
    assert "dotnet" in text.lower()
    # Positive: must call dotnet publish argv (CAST IRON: never build with csc alone).
    assert "'publish'" in text or '"publish"' in text
    assert "& $Dotnet @argv" in text or "& $Dotnet" in text
    assert "PublishSingleFile" in text
    assert "--self-contained" in text or "SelfContained" in text
    assert "win-x64" in text
    assert "SourceCommit" in text
    assert "GeneratedSourceCommit" in text
    assert "finally" in text
    assert "never csc" in text.lower() or "not Framework 4" in text
    assert "airc" in text.lower() or "no-SDK" in text


def test_fr9800_ci_workflow_setup_dotnet_and_pe():
    assert WF.is_file(), "missing .github/workflows/build-bob-worker-net.yml"
    text = _t(WF)
    assert "name: build-bob-worker-net" in text
    assert "runs-on: windows-latest" in text
    assert "setup-dotnet@v4" in text
    assert 'dotnet-version: "8.0.x"' in text or "dotnet-version: '8.0.x'" in text or "8.0.x" in text
    assert "Build-BobWorkerNet.ps1" in text
    assert "bob/scripts/Build-BobWorkerNet.ps1" in text
    assert "bob/worker/dotnet" in text
    assert "bob/tests/test_fr9800_bob_worker_net_build_ci.py" in text
    assert "persist-credentials: false" in text
    assert "upload-artifact@v4" in text
    assert "name: bob-worker-net" in text
    assert "bob-worker-net.exe" in text
    assert "--version" in text
    assert "SourceCommit" in text
    assert "WORKFLOW_COMMIT" in text
    assert "workflow_dispatch" in text
    assert "0x4D" in text or "MZ" in text  # PE check
    assert "provenance.txt" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    # Must not use Framework csc / setup for Framework-only.
    assert "csc.exe" not in text
    assert "Framework64" not in text


def test_fr9800_docs_airc_no_sdk_does_not_apply():
    assert DOCS.is_file(), "missing bob/docs/bob-worker-net.md"
    docs = _t(DOCS)
    assert "FR #9800" in docs
    assert "no-SDK" in docs or "no-SDK" in docs.replace(" ", "")
    assert "does **not** apply" in docs or "does not apply" in docs
    assert ".NET 8" in docs or "net8.0" in docs
    assert "Build-BobWorkerNet.ps1" in docs
    assert "build-bob-worker-net.yml" in docs
    assert "setup-dotnet" in docs
    assert "dotnet publish" in docs
    assert "csc.exe" in docs  # contrast documented
    assert "test_fr9800_bob_worker_net_build_ci.py" in docs
