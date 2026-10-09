"""MRB #3693 hostile pins for FR #3685 Install-Airc.cmd exit + outer fail report."""
from __future__ import annotations

from repo_layout import ROOT

CMD = ROOT / "airc/scripts/Install-Airc.cmd"
REPORTER = ROOT / "airc/scripts/Report-AircInstallCmdFailure.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"
PRODUCT = ROOT / "airc/tests/test_fr3685_install_cmd_fail_report.py"


def test_mrb3693_cmd_ec_capture_log_and_outer_reporter():
    t = CMD.read_text(encoding="utf-8")
    assert "set \"EC=%ERRORLEVEL%\"" in t
    assert "exit /b %EC%" in t
    assert "install-airc.log" in t
    assert "install-airc-fail-reported.flag" in t
    assert "Report-AircInstallCmdFailure.ps1" in t
    # Skip outer when PS Send already stamped the flag.
    assert "skip outer report" in t.lower() or "already reported" in t.lower()


def test_mrb3693_pack_cmd_call_wrap_and_return_check():
    p = PACK.read_text(encoding="utf-8-sig")
    assert "&quot;[System64Folder]cmd.exe&quot; /d /c call" in p
    assert 'Id="RunInstall"' in p
    assert 'Return="check"' in p
    assert "FR #3685" in p
    # Contiguous SetInstallCmd Value uses quoted cmd wrap (not bare .cmd path alone).
    i = p.find('Id="SetInstallCmd"')
    assert i >= 0
    window = p[i : i + 400]
    assert "&quot;[System64Folder]cmd.exe&quot; /d /c call" in window
    assert "$installArgs" in window


def test_mrb3693_fr70_pin_tracks_cmd_call_wrap():
    """FR #3715/#3741: keep FR #70 SetInstallCmd pin aligned with QuietExec-quoted cmd wrap."""
    fr70 = (ROOT / "common/tests/test_fr70_runinstall_msi_props.py").read_text(
        encoding="utf-8"
    )
    assert "&quot;[System64Folder]cmd.exe&quot; /d /c call" in fr70
    assert "$installArgs" in fr70
    assert "SetInstallCmd" in fr70


def test_mrb3693_outer_reporter_no_requires_and_redact():
    assert REPORTER.is_file()
    lines = REPORTER.read_text(encoding="utf-8").splitlines()
    assert not any(ln.strip().startswith("#Requires") for ln in lines)
    t = "\n".join(lines)
    assert "Redact-Fr3685CrashText" in t or "Redact" in t
    assert "BOBIVERSE_CRASH_REPORT" in t
    assert "SimonBarnett/bobiverse" in t
    assert "profile" in t.lower()


def test_mrb3693_send_helper_stamps_fail_flag():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Send-BobiverseAircInstallFailureIntake" in t
    send = t[t.find("function Send-BobiverseAircInstallFailureIntake") :]
    send = send[: send.find("\nfunction ", 1) if "\nfunction " in send[1:] else len(send)]
    assert "install-airc-fail-reported.flag" in send
    assert "Report-AircInstallCmdFailure.ps1" in t
    assert "Get-BobiverseAircClientAllowedScriptNames" in t
    allow = t[t.find("function Get-BobiverseAircClientAllowedScriptNames") :]
    allow = allow[: allow.find("\nfunction ", 1)]
    assert "Report-AircInstallCmdFailure.ps1" in allow


def test_mrb3693_docs_skill_and_product_tests():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3685" in skill or "#3685" in skill
    assert "Report-AircInstallCmdFailure" in skill
    assert "/d /c call" in skill
    assert "System64Folder" in skill or "3741" in skill
    post = POST.read_text(encoding="utf-8")
    assert "FR #3685" in post
    assert "Report-AircInstallCmdFailure" in post
    assert "/d /c call" in post
    assert "System64Folder" in post or "3741" in post
    assert "install-airc-fail-reported.flag" in post
    assert PRODUCT.is_file()
    # New FR #3685 skill/post paragraphs must stay UTF-8 (no mojibake in the window).
    si = skill.find("FR #3685")
    assert si >= 0 and "â" not in skill[si : si + 400]
    pi = post.find("FR #3685")
    assert pi >= 0 and "â" not in post[pi : pi + 500]
