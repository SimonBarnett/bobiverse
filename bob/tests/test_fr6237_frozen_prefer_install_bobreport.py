"""FR #6237: frozen bob-ear.exe prefers InstallRoot/scripts bobreport over _MEIPASS."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import irc_agent
from repo_layout import ROOT

START = ROOT / "bob" / "scripts" / "Start-Bob.ps1"
AGENT = ROOT / "common" / "scripts" / "irc_agent.py"
SMOKE = ROOT / "common" / "scripts" / "Assert-BobDigestHttpPullOk.ps1"


def test_prefer_install_scripts_noop_when_not_frozen(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bobreport.py").write_text("MARKER = 1\n", encoding="utf-8")
    path: list[str] = []
    got = irc_agent.prefer_install_scripts_path(
        env={"BOB_INSTALL_ROOT": str(install)},
        frozen=False,
        path_list=path,
    )
    assert got is None
    assert path == []


def test_prefer_install_scripts_inserts_install_scripts_when_frozen(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    install = tmp_path / "ai" / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bobreport.py").write_text('MARKER = "install"\n', encoding="utf-8")
    mei = tmp_path / "_MEI6237"
    mei.mkdir()
    path = [str(mei)]
    got = irc_agent.prefer_install_scripts_path(
        env={"BOB_INSTALL_ROOT": str(install)},
        frozen=True,
        path_list=path,
    )
    assert got == str(scripts.resolve())
    # The scripts directory must not move in front of the embed.
    assert path == [str(mei)]


def test_prefer_install_scripts_noop_without_on_disk_bobreport(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    install = tmp_path / "bob"
    (install / "scripts").mkdir(parents=True)
    path: list[str] = ["mei"]
    got = irc_agent.prefer_install_scripts_path(
        env={"BOB_INSTALL_ROOT": str(install)},
        frozen=True,
        path_list=path,
    )
    assert got is None
    assert path == ["mei"]


def test_prefer_install_scripts_from_exe_scripts_layout(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bobreport.py").write_text("X = 1\n", encoding="utf-8")
    exe = scripts / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    path: list[str] = []
    got = irc_agent.prefer_install_scripts_path(
        env={},
        frozen=True,
        executable=exe,
        path_list=path,
    )
    assert got == str(scripts.resolve())
    assert path == []


def test_prefer_install_scripts_path_order_loads_install_marker(tmp_path, monkeypatch):
    """Hostile: after prefer, path[0]/bobreport.py is the install marker (not _MEI)."""
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    install_py = scripts / "bobreport.py"
    install_py.write_text(
        'DIGEST_HTTP_USER_AGENT = "Bobiverse-bobreport/1.0"\nMARKER = "install"\n'
        "def opencode_install_root(env=None):\n    return None\n",
        encoding="utf-8",
    )
    mei = tmp_path / "_MEI"
    mei.mkdir()
    (mei / "bobreport.py").write_text(
        'DIGEST_HTTP_USER_AGENT = ""\nMARKER = "mei"\n',
        encoding="utf-8",
    )
    path: list[str] = [str(mei)]
    got = irc_agent.prefer_install_scripts_path(
        env={"BOB_INSTALL_ROOT": str(install)},
        frozen=True,
        path_list=path,
    )
    assert got == str(scripts.resolve())
    assert path == [str(mei)]
    finder = irc_agent._InstallScriptOverlay(scripts)
    spec = finder.find_spec("bobreport", None)
    assert spec is not None and spec.origin is not None
    assert Path(spec.origin).resolve() == install_py.resolve()
    assert finder.find_spec("gitclaim", None) is None
    spec = importlib.util.spec_from_file_location("bobreport_fr6237_probe", spec.origin)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.MARKER == "install"
    assert mod.DIGEST_HTTP_USER_AGENT == "Bobiverse-bobreport/1.0"


def test_reader_ignores_gitclaim_without_shop_line_reset(monkeypatch):
    monkeypatch.delattr(irc_agent.gitclaim, "shop_line_resets_bored_clock", raising=False)
    assert irc_agent._shop_line_resets_bored_clock("DONE job") is False


def test_reader_shop_line_reset_uses_gitclaim_when_present():
    assert irc_agent._shop_line_resets_bored_clock("DONE job") is True
    assert irc_agent._shop_line_resets_bored_clock("hello") is False


def test_fr6237_irc_agent_calls_prefer_before_import_bobreport():
    text = AGENT.read_text(encoding="utf-8")
    assert "def prefer_install_scripts_path" in text
    i_def = text.find("def prefer_install_scripts_path")
    i_call = text.find("_install_scripts = prefer_install_scripts_path(")
    i_imp = text.find("import bobreport  # noqa: E402")
    assert i_def > 0 and i_call > i_def and i_imp > i_call
    assert "FR #6237" in text


def test_fr6237_start_bob_exports_install_root_before_ear_exe():
    """Prefer-install needs BOB_INSTALL_ROOT (FR 2266) before bob-ear.exe starts."""
    t = START.read_text(encoding="utf-8-sig")
    i_env = t.lower().find("bob_install_root")
    i_launch = t.find("& $earExe")
    if i_launch < 0:
        i_launch = t.find("via=bob-ear.exe")
    assert i_env > 0 and i_launch > 0 and i_env < i_launch


def test_fr6237_digest_http_pull_ok_smoke_script_exists():
    assert SMOKE.is_file()
    t = SMOKE.read_text(encoding="utf-8-sig")
    assert "digest http pull ok" in t
    assert "FR #6237" in t or "6237" in t


def test_fr6237_assert_digest_pull_ok_helper_parses_log(tmp_path):
    """Unit smoke: helper returns ok when stdout log shows digest http pull ok."""
    import assert_bob_digest_http_pull_ok as smoke

    log = tmp_path / "stdout.log"
    log.write_text(
        "INFO connected\nINFO digest http pull failed\nINFO digest http pull ok url=https://example.test/digest\n",
        encoding="utf-8",
    )
    r = smoke.scan_stdout_log(log)
    assert r["ok"] is True
    assert "digest http pull ok" in r["line"]


def test_fr6237_assert_digest_pull_ok_helper_fails_without_ok(tmp_path):
    import assert_bob_digest_http_pull_ok as smoke

    log = tmp_path / "stdout.log"
    log.write_text("INFC digest http pull failed\n", encoding="utf-8")
    r = smoke.scan_stdout_log(log)
    assert r["ok"] is False


def test_fr6237_start_bob_does_not_skip_exe_on_bobreport_mtime():
    """FR #7233: Start-Bob must not skip bob-ear.exe because bobreport.py is newer.

    Hotpatched bobreport still applies inside a rebuilt/frozen ear via
    prefer_install_scripts_path (the rest of this module).
    """
    t = START.read_text(encoding="utf-8-sig")
    assert "bobreport.py newer than bob-ear.exe" not in t
    assert "Select-BobEarLaunch" in t
    i_env = t.lower().find("bob_install_root")
    i_launch = t.find("& $earExe")
    if i_launch < 0:
        i_launch = t.find("via=bob-ear.exe")
    assert i_env > 0 and i_launch > 0 and i_env < i_launch
