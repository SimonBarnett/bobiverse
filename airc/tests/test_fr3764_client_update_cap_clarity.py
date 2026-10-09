"""FR #3764: client update=on vs self-update=off is intentional - clarify logs/docs.

``capabilities update=`` gates the remote UPDATE verb (ops-gated, FR #3401).
``self-update=`` / ``sync_from_repo=`` are start-time automatic channels (off on client).
"""
from __future__ import annotations

import airc_console as ac
from repo_layout import ROOT

POST = ROOT / "common" / "docs" / "post-install.md"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)
INSTALL = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
CONSOLE = ROOT / "airc" / "scripts" / "airc_console.py"


def test_fr3764_client_defaults_update_on_self_update_off():
    assert (
        ac.resolve_update_cap_for_install(prior="off", explicit=None, profile="client")
        == "on"
    )
    assert (
        ac.resolve_self_update_for_install(prior=True, explicit=None, profile="client")
        is False
    )
    # FR #3462 sync force-off for client is in Install-Airc.ps1 (pinned below).


def test_fr3764_capabilities_log_distinguishes_remote_update():
    line = ac.ConsoleCapabilities(update="on").log_line()
    assert line.startswith("INFO capabilities shell=")
    assert "update=on" in line
    assert "remote" in line.lower()
    assert "self-update" in line.lower() or "not auto" in line.lower()
    # Must not imply automatic MSI self-update is on.
    assert "auto self-update=on" not in line.lower()


def test_fr3764_install_and_docs_pins():
    inst = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3401 ops-gated UPDATE" in inst or "ops-gated UPDATE" in inst
    assert "prof -eq 'client') { $resolvedUpdate = 'on'" in inst.replace(" ", "") or (
        "elseif ($prof -eq 'client') { $resolvedUpdate = 'on' }" in inst
    )
    assert "elseif ($prof -in @('workstation', 'client')) { $resolvedSelf = $false }" in inst
    post = POST.read_text(encoding="utf-8")
    assert "FR #3764" in post
    assert "remote UPDATE" in post or "ops-gated" in post
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3764" in skill
    text = CONSOLE.read_text(encoding="utf-8")
    assert "FR #3764" in text
    assert "remote UPDATE" in text or "ops-gated remote" in text.lower()
