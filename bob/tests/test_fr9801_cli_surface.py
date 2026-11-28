"""FR #9801: bob-worker-net tray argv, JSON stubs, unknown mode."""
from __future__ import annotations

from repo_layout import ROOT

CLI = ROOT / "bob" / "worker" / "dotnet" / "CliArgs.cs"
PROG = ROOT / "bob" / "worker" / "dotnet" / "Program.cs"
DOC = ROOT / "bob" / "docs" / "bob-worker-net.md"


def test_fr9801_parser_flags_and_modes():
    text = CLI.read_text(encoding="utf-8")
    for flag in (
        "--mode",
        "--install-root",
        "--machine-id",
        "--agent",
        "--list-agents",
        "--dry-run",
        "--echo",
    ):
        assert flag in text
    for mode in ("agent", "plan", "monitor", "maintenance", "jeeves"):
        assert '"' + mode + '"' in text
    assert "unknown mode" in text
    assert "unknown argument" in text
    assert "UsageExit = 64" in text


def test_fr9801_json_stub_shape():
    text = CLI.read_text(encoding="utf-8")
    for key in ("id", "label", "available", "installed", "fuel_state", "reason", "refresh", "stub"):
        assert key in text
    dry = ("mode", "agent", "install_root", "machine_id", "echo", "started")
    for key in dry:
        assert key in text
    prog = PROG.read_text(encoding="utf-8")
    assert "CliArgs.ListAgentsJson()" in prog
    assert "CliArgs.DryRunJson" in prog
    assert "return 64" in prog


def test_fr9801_docs_name_the_dual_build():
    doc = DOC.read_text(encoding="utf-8")
    assert "bob-worker-net.exe" in doc
    assert "FR #9801" in doc
    assert "--list-agents" in doc
    assert "--dry-run" in doc
    assert "until cutover" in doc
