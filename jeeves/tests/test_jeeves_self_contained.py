"""#53 (complete): jeeves MSI is self-contained - no agentic_irc paths/env/modules; home migration;
report.secret generation; webhook bits packaged."""
import json
import re
from pathlib import Path

import pytest

import bob_home


@pytest.fixture(autouse=True)
def _isolated_profiles(monkeypatch, tmp_path_factory):
    """Never see this machine's real ~\\.agentic-irc-* homes."""
    fake = tmp_path_factory.mktemp("profiles")
    monkeypatch.setattr(bob_home, "_profile", lambda: fake / "me")
    monkeypatch.setattr(bob_home, "_admin_profile", lambda: fake / "Administrator")


from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service
SCRIPTS = ROOT / "scripts"
AIRC_PRODUCT = re.compile(r"airc_console|AircConsole|Install-Airc|Pack-AircConsole|Fetch-Nssm|Resolve-AircConsole", re.I)


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", errors="replace")


# ---------------------------------------------------------------- no agentic_irc dependency
def test_no_agentic_irc_env_or_home_names_in_jeeves_bob_code():
    bad = re.compile(r"AGENTIC_IRC_|\.agentic-irc-|AGENTIC_IRC\b")
    offenders = []
    for p in list(SCRIPTS.glob("*")) + list((ROOT / "tools").glob("*")):
        if not p.is_file() or p.suffix.lower() not in (".py", ".ps1", ".cmd") or AIRC_PRODUCT.search(p.name):
            continue
        if p.name in ("bob_home.py", "bob_git_hook.py", "Assert-BobDigestWebhookLocal.ps1"):
            # Legacy-home compatibility readers intentionally name old homes;
            # they do not make the packaged Jeeves service depend on agentic_irc.
            continue
        for i, line in enumerate(_text(p).splitlines(), 1):
            if bad.search(line) and not re.search(r"(?i)migrat|backup", line):
                offenders.append(f"{p.name}:{i}")
    assert not offenders, offenders


def test_no_agentic_irc_repo_or_module_dependency():
    t = _text(SCRIPTS / "intake.py")
    assert "agentic_irc" not in t
    assert "SimonBarnett/bobiverse" in t
    # nothing imports an agentic_irc module
    for p in SCRIPTS.glob("*.py"):
        if AIRC_PRODUCT.search(p.name):
            continue
        assert not re.search(r"^\s*(import|from)\s+agentic_irc", _text(p), re.M), p.name


def test_home_defaults_are_jeeves_and_bobiverse(monkeypatch, tmp_path):
    for k in ("BOB_HOME", "BOB_DIGEST_HOME"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.undo()  # keep env isolation below, drop the profile stubs for this test
    monkeypatch.delenv("BOB_HOME", raising=False)
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert bob_home.chair_home() == tmp_path / ".jeeves"
    assert bob_home.digest_home() == tmp_path / ".bobiverse"
    import seal
    assert seal.home().name == ".bobiverse"
    monkeypatch.setenv("BOB_HOME", str(tmp_path / "x"))
    assert seal.home() == tmp_path / "x"


def test_bobreport_default_digest_home_is_bobiverse(monkeypatch, tmp_path):
    import bobreport
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    (tmp_path / ".bobiverse").mkdir()
    assert bobreport._default_digest_home() == tmp_path / ".bobiverse"
    assert bobreport.DIGEST_URL_ENV == "BOB_DIGEST_URL"
    assert bobreport.CHAIR_NICK_ENV == "BOB_CHAIR_NICK"


# ---------------------------------------------------------------- migration
def _old_home(tmp_path):
    old = tmp_path / ".agentic-irc-bobiverse"
    old.mkdir()
    (old / "digest.json").write_text(json.dumps({"machines": {"x": {}}}), encoding="utf-8")
    for n in ("focus.json", "ignored.json", "queue.json", "registered-machines.json"):
        (old / n).write_text("{}", encoding="utf-8")
    (old / "nickserv.password").write_text("s3cret-nick", encoding="utf-8")
    (old / "irc.log").write_text("noise", encoding="utf-8")
    sub = old / "bob-peers"
    sub.mkdir()
    (sub / "m.json").write_text("{}", encoding="utf-8")
    return old


def test_migration_moves_data_keeps_old_as_backup_and_is_idempotent(tmp_path, capsys):
    old = _old_home(tmp_path)
    new = tmp_path / ".bobiverse"
    res = bob_home.migrate_legacy(new)
    assert res["status"] == "migrated"
    for n in ("digest.json", "focus.json", "ignored.json", "queue.json", "registered-machines.json", "nickserv.password"):
        assert (new / n).is_file(), n
    assert (new / "bob-peers" / "m.json").is_file()
    assert not (new / "irc.log").exists()  # live-state log is not migrated
    assert old.is_dir() and (old / "digest.json").is_file()  # backup untouched
    assert sorted(res["key_files"]) == sorted(bob_home.KEY_FILES)
    assert "nickserv.password" in res["secret_files"]
    assert "s3cret-nick" not in json.dumps(res) and "s3cret-nick" not in capsys.readouterr().out
    # second start: marker, nothing re-copied even if the new file changed
    (new / "digest.json").write_text('{"changed": 1}', encoding="utf-8")
    again = bob_home.migrate_legacy(new)
    assert again["status"] == "already"
    assert json.loads((new / "digest.json").read_text())["changed"] == 1


def test_migration_never_overwrites_existing_new_files(tmp_path):
    old = _old_home(tmp_path)
    new = tmp_path / ".bobiverse"
    new.mkdir()
    (new / "digest.json").write_text('{"new": true}', encoding="utf-8")
    res = bob_home.migrate_legacy(new)
    assert json.loads((new / "digest.json").read_text()) == {"new": True}
    assert (new / "digest.json.legacy").is_file()  # old copy preserved next to it
    assert "digest.json" in res["conflicts"]


def test_chair_home_migrates_from_agentic_irc_jeeves(tmp_path):
    old = tmp_path / ".agentic-irc-jeeves"
    old.mkdir()
    (old / "operators.txt").write_text("Simon\n", encoding="utf-8")
    (old / "github.token").write_text("tok", encoding="utf-8")
    (old / "agent.quit.request").write_text("x", encoding="utf-8")
    res = bob_home.migrate_legacy(tmp_path / ".jeeves", role="chair")
    assert res["status"] == "migrated"
    assert (tmp_path / ".jeeves" / "operators.txt").read_text() == "Simon\n"
    assert not (tmp_path / ".jeeves" / "agent.quit.request").exists()


def test_migration_custom_home_uses_role(tmp_path):
    old = tmp_path / ".agentic-irc-jeeves"
    old.mkdir()
    (old / "accounts.json").write_text("{}", encoding="utf-8")
    custom = tmp_path / "install" / "home-jeeves"
    assert bob_home.migrate_legacy(custom)["status"] == "no-legacy"  # unknown role: nothing guessed
    assert bob_home.migrate_legacy(custom, old_homes=[old])["status"] == "migrated"


def test_no_legacy_home_is_a_noop(tmp_path):
    assert bob_home.migrate_legacy(tmp_path / ".bobiverse")["status"] == "no-legacy"
    assert not (tmp_path / ".bobiverse").exists()


def test_optional_github_token_copied_into_install_config_once_and_report_secret_never(tmp_path):
    prof = tmp_path / "Administrator"
    (prof / ".grok" / "bob").mkdir(parents=True)
    (prof / ".grok" / "bob" / "report.secret").write_text("RS", encoding="utf-8")
    (prof / ".grok" / "bob" / "github.token").write_text("GT0", encoding="utf-8")
    cfg = tmp_path / "install" / "config"
    got = bob_home.migrate_secrets_to_config(cfg, profiles=[prof])
    assert got == ["github.token"] and (cfg / "github.token").read_text() == "GT0"
    assert not (cfg / "report.secret").exists()  # v0.1.16: webhooks use no report.secret
    (cfg / "github.token").write_text("NEW", encoding="utf-8")
    assert bob_home.migrate_secrets_to_config(cfg, profiles=[prof]) == []
    assert (cfg / "github.token").read_text() == "NEW"
    cfg2 = tmp_path / "install2" / "config"
    # from a migrated home
    home = tmp_path / "h"
    home.mkdir()
    (home / "github.token").write_text("GT", encoding="utf-8")
    assert bob_home.migrate_secrets_to_config(cfg2, profiles=[], homes=[home]) == ["github.token"]


# ---------------------------------------------------------------- installer / packaging
def test_install_jeeves_needs_and_generates_no_webhook_secret():
    t = _text(SCRIPTS / "Install-Jeeves.ps1")
    assert "RandomNumberGenerator" not in t and "report.secret" not in t and "--secret-file" not in t
    assert "no password/secret required" in t
    assert "/TN BobCallback" in t and "Install-BobWebhooks.ps1" in t
    assert "BOB_CONFIG_DIR=$cfgDir" in t and "BOB_HOME=$ChairHome" in t
    assert "bob_home.py" in t and "migrate" in t


def test_pack_stages_tools_for_jeeves_and_webhook_files_exist():
    pack = _text(SCRIPTS / "Pack-BobiverseRelease.ps1")
    assert "bob_git_hook.py" in pack and "New-BobGitWebhook.ps1" in pack
    for n in ("bobcallback.py", "gh_filer.py", "intake.py", "jira_webhook.py", "webhook_queue.py",
              "Install-BobWebhooks.ps1", "Watch-BobWebhooks.ps1", "Start-BobCallback.cmd", "bob_home.py", "chair_oper.py"):
        assert (SCRIPTS / n).is_file(), n
    for n in ("bob_git_hook.py", "New-BobGitWebhook.ps1"):
        assert (ROOT / "tools" / n).is_file()


def test_callback_cmd_and_watchers_use_install_relative_config():
    cb = _text(SCRIPTS / "Start-BobCallback.cmd")
    assert "BOB_CONFIG_DIR" in cb and "report.secret" not in cb and "--secret-file" not in cb and "Administrator" not in cb
    wh = _text(SCRIPTS / "Watch-BobWebhooks.ps1")
    assert ".agentic-irc" not in wh and "'.bobiverse'" in wh


def test_gh_token_candidates_include_install_config_env(monkeypatch, tmp_path):
    import gh_filer
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("BOB_CONFIG_DIR", str(cfg))
    assert gh_filer._token_candidate_paths()[0] == cfg / "github.token"


def test_stage_for_jeeves_includes_tools():
    pack = _text(SCRIPTS / "Pack-BobiverseRelease.ps1")
    seg = pack.split("if ($Name -eq 'jeeves') {", 1)[1]
    assert "tools" in seg.split("if ($Name -eq 'bob')", 1)[0]
