"""FR #3639: fleet airc authorises by IRC +o/+h only - no operators list."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

import airc_console as ac
from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
SERVICE = ROOT / "airc/scripts/airc_console_service.py"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def _ascii_only(path: Path) -> None:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    assert all(b < 128 for b in raw), f"non-ASCII in {path}"


def _ps(script: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(ROOT),
    )


def test_install_fleet_writes_irc_ops_and_skips_operators_union():
    t = INSTALL.read_text(encoding="utf-8-sig")
    _no_bom(INSTALL)
    _ascii_only(INSTALL)
    assert "FR #3639" in t
    assert "profForOps -in @('client', 'fleet')" in t
    assert "$authMode = $(if ($prof -in @('client', 'fleet')) { 'irc_ops' }" in t
    assert "AuthMode    = $(if ($prof -in @('client', 'fleet')) { 'irc_ops' }" in t


def test_service_defaults_fleet_profile_to_irc_ops():
    t = SERVICE.read_text(encoding="utf-8")
    assert "FR #3639" in t or "#3639" in t
    assert 'prof in ("client", "fleet")' in t


def test_resolve_fleet_returns_empty_like_client():
    common = COMMON.read_text(encoding="utf-8-sig")
    chunk = common[common.find("Resolve-BobiverseAircOperatorNicks") :][:3200]
    assert "FR #3639" in chunk
    assert "client', 'fleet'" in chunk


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_resolve_fleet_empty_ignores_roster_and_extra(tmp_path: Path):
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "fleet-operators.txt").write_text(
        "# comment\nbob-win-mpre8vi4u6u\n", encoding="utf-8"
    )
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $ops = Resolve-BobiverseAircOperatorNicks -Profile 'fleet' `
            -Operators @('Simon') -OperatorsExtra 'bob-evil' -InstallRoot '{root}'
        $join = (@($ops) -join ',')
        if ($join) {{ throw "fleet must return empty ops under FR #3639: $join" }}
        $cli = Resolve-BobiverseAircOperatorNicks -Profile 'client' `
            -Operators @('Simon') -OperatorsExtra 'bob-evil' -InstallRoot '{root}'
        if ((@($cli) -join ',')) {{ throw "client must stay empty" }}
        $ws = Resolve-BobiverseAircOperatorNicks -Profile 'workstation' `
            -Operators @('Simon') -OperatorsExtra 'bob-evil' -InstallRoot '{root}'
        $wsj = (@($ws) -join ',')
        if ($wsj -notmatch '(?i)^Simon$') {{ throw "workstation ops unexpected: $wsj" }}
        Write-Output 'ok'
        """
    )
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok" in (r.stdout or "")


def test_fleet_irc_ops_deny_not_op_matches_client():
    m = ac.ChannelMemberMap(channel="#marchhare")
    m.apply_names("@simon plain")
    m.mark_synced()
    auth = ac.AuthPolicy(
        auth_mode="irc_ops",
        members=m,
        self_nicks={"marchhare_console"},
        machine="marchhare",
    )
    core = ac.AircConsoleCore(
        machine="marchhare", auth=auth, nick="marchhare_console"
    )
    core.channel = "#marchhare"
    hr = core.handle_raw(":simon!u@h PRIVMSG #marchhare :STATUS")
    assert hr is not None
    assert hr.action in ("job", "pipe", "shell")
    hr = core.handle_raw(":plain!u@h PRIVMSG marchhare_console :Write-Output hi")
    assert hr is not None
    assert hr.action == "deny"
    assert hr.reply == "DONE exit=126 not-op"


def test_docs_skill_fleet_irc_ops():
    post = POST.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    blob = post + "\n" + skill
    assert "3639" in blob
    assert "irc_ops" in blob or "+o" in blob or "half-op" in blob.lower()
