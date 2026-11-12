"""FR #6947: chair starts only on walrus; never Jeeves_l; no ircJeeves on seats."""
from __future__ import annotations

import argparse
import io
from contextlib import redirect_stderr
from pathlib import Path

import jeeves_chair_host as jch
import jeeves_main
from repo_layout import ROOT


def test_fr6947_guard_refuses_non_walrus():
    env = {"COMPUTERNAME": "redqueen", "BOB_MACHINE_ID": "redqueen"}
    assert jch.configured_chair_host(env) == "walrus"
    assert jch.this_host_id(env) == "redqueen"
    assert jch.chair_host_allowed(env=env) is False
    line = jch.refuse_chair_host_line(env=env)
    assert "CHAIR_HOST_REFUSED" in line
    assert "redqueen" in line
    assert "walrus" in line
    assert "6947" in line


def test_fr6947_guard_allows_walrus():
    env = {"COMPUTERNAME": "WALRUS", "BOB_MACHINE_ID": ""}
    assert jch.chair_host_allowed(env=env) is True
    env2 = {"BOB_MACHINE_ID": "walrus", "COMPUTERNAME": "other"}
    assert jch.chair_host_allowed(env=env2) is True


def test_fr6947_chair_host_env_is_not_a_cli_flag():
    env = {"JEEVES_CHAIR_HOST": "walrus", "COMPUTERNAME": "walrus"}
    assert jch.configured_chair_host(env) == "walrus"
    irc = (ROOT / "common/scripts/irc_agent.py").read_text(encoding="utf-8")
    jm = (ROOT / "common/scripts/jeeves_main.py").read_text(encoding="utf-8")
    assert "--chair-host" not in irc
    assert "--chair-host" not in jm
    assert 'add_argument("--chair-host"' not in irc
    assert 'add_argument("--chair-host"' not in jm


def test_fr6947_nick_taken_exits_not_suffix():
    assert jch.chair_nick_in_use_must_exit(True) is True
    assert jch.chair_nick_in_use_must_exit(False) is False
    line = jch.chair_nick_taken_line("Jeeves")
    assert "CHAIR_NICK_TAKEN" in line
    assert "Jeeves_l" not in line
    src = (ROOT / "common/scripts/irc_agent.py").read_text(encoding="utf-8")
    assert "chair_nick_in_use_must_exit" in src
    assert "CHAIR_NICK_TAKEN" in src
    assert "_no_reconnect" in src
    # Suffixed fallback remains for non-chair generic nicks, not for --chair.
    chair_block = src.split("if cmd in (\"433\", \"432\"):", 1)[1][:900]
    assert "chair_nick_in_use_must_exit" in chair_block
    assert 'original_nick + "_l"' in src


def test_fr6947_jeeves_main_chair_refuses_wrong_host(monkeypatch, tmp_path):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("COMPUTERNAME", "flamingo")
    monkeypatch.setenv("BOB_MACHINE_ID", "flamingo")
    monkeypatch.delenv("JEEVES_CHAIR_HOST", raising=False)
    err = io.StringIO()
    with redirect_stderr(err):
        code = jeeves_main.main(["--chair", "--http", "127.0.0.1:7700"])
    assert code == jch.EXIT_WRONG_HOST
    assert "CHAIR_HOST_REFUSED" in err.getvalue()


def test_fr6947_install_skips_service_on_seat_machine():
    inst = (ROOT / "jeeves/scripts/Install-Jeeves.ps1").read_text(encoding="utf-8")
    common = (ROOT / "common/scripts/Bobiverse-Common.ps1").read_text(encoding="utf-8")
    start = (ROOT / "jeeves/scripts/Start-Jeeves.ps1").read_text(encoding="utf-8")
    assert "Test-BobiverseIsChairHost" in inst
    assert "Disable-BobiverseStrayChairService" in inst
    assert "FR #6947" in inst
    assert "nssm" in inst.lower() or "Invoke-BobiverseNssmChecked" in inst
    assert "InstallChairService" in inst
    assert "function Test-BobiverseIsChairHost" in common
    assert "function Disable-BobiverseStrayChairService" in common
    assert "stopped" in common.lower() and "disabled" in common.lower()
    assert "Test-BobiverseIsChairHost" in start
    assert "CHAIR_HOST_REFUSED" in start
    assert "--chair-host" not in inst


def test_fr6947_irc_agent_parse_has_no_chair_host_flag():
    p = argparse.ArgumentParser()
    # Source pin: help text documents walrus-only via jeeves_chair_host, not a seat flag.
    src = (ROOT / "common/scripts/irc_agent.py").read_text(encoding="utf-8")
    assert "jeeves_chair_host" in src
    assert "chair_host_allowed" in src
    assert Path(ROOT / "common/scripts/jeeves_chair_host.py").is_file()
    _ = p
