"""MRB #3911 hostile pins for FR #3904 bob upgrade Ergo/nickserv/AppStdout.

After product merge #3911:
- Sibling airc/jeeves ergo.password resolve + seed
- Ensure-BobiverseBobNickServPassword migrate + fail-closed
- Install-Bob prior AppParameters before Remove; AppStdout under logs
- irc_agent crash-reports NICKNAME_RESERVED once
- Skills UTF-8 without mojibake (jeeves\\config\\ergo.password contiguous)
"""
from __future__ import annotations

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
INSTALL = ROOT / "bob" / "scripts" / "Install-Bob.ps1"
IRC_AGENT = ROOT / "common" / "scripts" / "irc_agent.py"
POST = ROOT / "common" / "docs" / "post-install.md"
TROUBLE = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"
BOB_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"
PRODUCT_PIN = ROOT / "bob" / "tests" / "test_fr3904_upgrade_nickserv_ergo_logs.py"


def test_mrb3911_common_sibling_ergo_and_nickserv_ensure():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "FR #3904" in t
    assert "function Get-BobiverseErgoPasswordPath" in t
    assert r"airc\config\ergo.password" in t
    assert r"jeeves\config\ergo.password" in t
    assert "function Seed-BobiverseErgoPassword" in t
    assert "function Ensure-BobiverseBobNickServPassword" in t
    assert "never mint a fresh GUID" in t or "never mint" in t.lower()


def test_mrb3911_install_order_appstdout_fail_closed():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3904" in t
    i_prior = t.find("$priorAppParams = Get-BobiverseServiceAppParameters")
    i_remove = t.find("Remove-BobiverseService -Nssm")
    assert i_prior > 0 and i_remove > i_prior
    assert "Ensure-BobiverseBobNickServPassword" in t
    assert "FailIfMissing" in t
    assert "AppStdout" in t and "AppStderr" in t
    assert "AppStdoutCreationDisposition" in t


def test_mrb3911_irc_agent_nickname_reserved_crash_report():
    t = IRC_AGENT.read_text(encoding="utf-8")
    assert "NICKNAME_RESERVED" in t
    assert "FR #3904" in t or "3904" in t
    assert "report_exception" in t
    # one-shot gate
    assert "_nickname_reserved_reported" in t or "nickname_reserved" in t.lower()


def test_mrb3911_skills_docs_utf8_no_mojibake():
    trouble = TROUBLE.read_text(encoding="utf-8")
    assert "FR #3904" in trouble
    assert r"jeeves\config\ergo.password" in trouble
    assert "\ufffd" not in trouble
    assert not TROUBLE.read_bytes().startswith(b"\xef\xbb\xbf")

    bob = BOB_SKILL.read_text(encoding="utf-8")
    assert "FR #3904" in bob
    assert "AppStdout" in bob
    assert "\ufffd" not in bob
    assert "->" in bob or "logs\\stdout.log" in bob

    post = POST.read_text(encoding="utf-8")
    assert "FR #3904" in post
    assert not POST.read_bytes().startswith(b"\xef\xbb\xbf")

    assert PRODUCT_PIN.is_file()
