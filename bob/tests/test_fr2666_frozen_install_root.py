"""FR #2666: frozen bob-ear.exe must resolve install root from sys.executable, not _MEIPASS."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import irc_agent
from repo_layout import ROOT

BOB = ROOT / "bob"
START = BOB / "scripts" / "Start-Bob.ps1"


def test_resolve_bob_install_root_env_override(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    want = tmp_path / "bob-install"
    want.mkdir()
    got = irc_agent.resolve_bob_install_root(env={"BOB_INSTALL_ROOT": str(want)}, frozen=True)
    assert got == want.resolve()


def test_resolve_bob_install_root_frozen_scripts_layout(tmp_path, monkeypatch):
    """PyInstaller onefile: __file__ under _MEI*; exe at <InstallRoot>\\scripts\\bob-ear.exe."""
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    install = tmp_path / "ai" / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    exe = scripts / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    mei = tmp_path / "_MEI000034a02"
    mei.mkdir()
    fake_file = mei / "irc_agent.pyc"
    fake_file.write_bytes(b"")

    # Bug class: Path(__file__).parent.parent under _MEI -> parent of extract dir.
    buggy = Path(fake_file).resolve().parent.parent
    assert buggy != install.resolve()

    got = irc_agent.resolve_bob_install_root(
        env={},
        frozen=True,
        executable=exe,
        file_path=fake_file,
    )
    assert got == install.resolve()


def test_resolve_bob_install_root_frozen_flat_exe_parent(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    install = tmp_path / "bob"
    install.mkdir()
    exe = install / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    got = irc_agent.resolve_bob_install_root(env={}, frozen=True, executable=exe)
    assert got == install.resolve()


def test_resolve_bob_install_root_source_scripts_parent(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    src = scripts / "irc_agent.py"
    src.write_text("# stub\n", encoding="utf-8")
    got = irc_agent.resolve_bob_install_root(env={}, frozen=False, file_path=src)
    assert got == install.resolve()


def test_irc_agent_install_root_uses_args_explicit(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    want = tmp_path / "explicit-root"
    want.mkdir()
    agent = irc_agent.Client.__new__(irc_agent.Client)
    agent.args = SimpleNamespace(install_root=str(want))
    assert agent._install_root() == want.resolve()


def test_start_bob_exports_bob_install_root():
    t = START.read_text(encoding="utf-8-sig")
    assert "BOB_INSTALL_ROOT" in t
    assert "FR #2666" in t or "2666" in t
    # Env export must run before launching bob-ear.exe so older frozen ears see the queue dir.
    # Do not require --install-root on the argv: unknown flag aborts pre-#2666 bob-ear.exe.
    i_env = t.lower().find("bob_install_root")
    i_launch = t.find("& $earExe")
    if i_launch < 0:
        i_launch = t.find("via=bob-ear.exe")
    assert i_env > 0 and i_launch > 0 and i_env < i_launch
    # Still document / keep argparse --install-root in irc_agent for explicit/new ears.
    agent = (ROOT / "common" / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "--install-root" in agent
    assert "resolve_bob_install_root" in agent


# --- MRB #2671 hostile additions ---


def test_mrb2671_explicit_beats_env_and_frozen(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    want = tmp_path / "explicit"
    other = tmp_path / "env-root"
    want.mkdir()
    other.mkdir()
    exe = (tmp_path / "scripts")
    exe.mkdir()
    ear = exe / "bob-ear.exe"
    ear.write_bytes(b"MZ")
    got = irc_agent.resolve_bob_install_root(
        explicit=want,
        env={"BOB_INSTALL_ROOT": str(other)},
        frozen=True,
        executable=ear,
    )
    assert got == want.resolve()


def test_mrb2671_blank_explicit_falls_through_to_env(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    want = tmp_path / "from-env"
    want.mkdir()
    got = irc_agent.resolve_bob_install_root(
        explicit="   ",
        env={"BOB_INSTALL_ROOT": str(want)},
        frozen=True,
    )
    assert got == want.resolve()


def test_mrb2671_client_empty_install_root_uses_env(tmp_path, monkeypatch):
    want = tmp_path / "env-client"
    want.mkdir()
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(want))
    agent = irc_agent.Client.__new__(irc_agent.Client)
    agent.args = SimpleNamespace(install_root="")
    assert agent._install_root() == want.resolve()


def test_mrb2671_frozen_mei_queue_dir_is_under_install_root(tmp_path, monkeypatch):
    """Hostile: startworker.queue_dir must not land under Temp when __file__ is _MEI*."""
    import startworker as sw

    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    install = tmp_path / "ai" / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    exe = scripts / "bob-ear.exe"
    exe.write_bytes(b"MZ")
    mei = tmp_path / "_MEIhostile"
    mei.mkdir()
    fake = mei / "irc_agent.pyc"
    fake.write_bytes(b"")
    root = irc_agent.resolve_bob_install_root(
        env={},
        frozen=True,
        executable=exe,
        file_path=fake,
    )
    q = sw.queue_dir(root)
    assert root == install.resolve()
    assert q == (install / "run" / "startworker").resolve()
    assert "_MEI" not in str(q)
