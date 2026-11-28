"""FR #10100 harvest: GHA pwsh must quote Build-BobDialogs -Targets comma lists."""
from __future__ import annotations

from repo_layout import ROOT


def test_build_bob_tray_workflow_quotes_targets():
    wf = (ROOT / ".github" / "workflows" / "build-bob-tray.yml").read_text(
        encoding="utf-8"
    )
    assert '-Targets "tray,about"' in wf
    assert "-Targets tray,about" not in wf.replace('-Targets "tray,about"', "")


def test_build_bob_msi_workflow_quotes_targets():
    wf = (ROOT / ".github" / "workflows" / "build-bob-msi.yml").read_text(
        encoding="utf-8"
    )
    assert '-Targets "tray,about"' in wf


def test_harvest_docs_mention_pwsh_quoting():
    docs = (ROOT / "bob" / "docs" / "bob-tray-dialogs.md").read_text(encoding="utf-8")
    assert "10100" in docs
    assert 'Targets "tray,about"' in docs or '-Targets "tray,about"' in docs