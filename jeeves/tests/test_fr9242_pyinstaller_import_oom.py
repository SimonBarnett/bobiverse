"""FR #9242: MemoryError during heavy jeeves import retries once then exits 1."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import jeeves_main  # noqa: E402


def test_import_heavy_retries_once_then_ok(monkeypatch):
    calls = {"n": 0}
    real_import = importlib.import_module

    def boom_then_ok(name, package=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise MemoryError("Unable to allocate output buffer.")
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", boom_then_ok)
    mod = jeeves_main.import_heavy("types")
    assert calls["n"] == 2
    assert mod is not None
    assert mod.__name__ == "types"


def test_import_heavy_re_raises_persistent_oom(monkeypatch):
    def always_oom(name, package=None):
        raise MemoryError("Unable to allocate output buffer.")

    monkeypatch.setattr(importlib, "import_module", always_oom)
    with pytest.raises(MemoryError, match="Unable to allocate"):
        jeeves_main.import_heavy("irc_agent")


def test_main_returns_1_when_irc_agent_oom(monkeypatch, tmp_path):
    """Chair path: persistent MemoryError loading irc_agent -> exit 1 (NSSM restart)."""
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setattr(jeeves_main, "harden_stdio_replace", lambda: None)
    monkeypatch.setattr(jeeves_main, "resolve_digest_home", lambda **kw: home)
    monkeypatch.setattr(jeeves_main, "resolve_chair_home", lambda **kw: home)
    monkeypatch.setattr(jeeves_main, "is_ephemeral_test_home", lambda p: False)

    locks = mock.Mock()
    locks.enable_inproc_locks = mock.Mock()
    locks.try_acquire_instance_mutex = mock.Mock(return_value=True)
    locks.release_instance_mutex = mock.Mock()

    httpd = mock.Mock()
    httpd.server_address = ("127.0.0.1", 17700)

    def fake_heavy(name: str):
        if name == "jeeves_locks":
            return locks
        if name == "gitclaim":
            return mock.Mock()
        if name == "bobcallback":
            return mock.Mock()
        if name == "irc_agent":
            raise MemoryError("Unable to allocate output buffer.")
        raise AssertionError(f"unexpected import_heavy({name!r})")

    monkeypatch.setattr(jeeves_main, "import_heavy", fake_heavy)
    monkeypatch.setattr(
        jeeves_main,
        "start_http_thread",
        lambda *a, **k: (mock.Mock(), httpd),
    )
    monkeypatch.setattr(
        "jeeves_chair_host.chair_host_allowed",
        lambda: True,
        raising=False,
    )

    # Avoid real chair_host import path by stubbing the module on sys.modules
    host_mod = mock.Mock()
    host_mod.chair_host_allowed = lambda: True
    host_mod.refuse_chair_host_line = lambda: "refuse"
    host_mod.EXIT_WRONG_HOST = 3
    monkeypatch.setitem(sys.modules, "jeeves_chair_host", host_mod)
    monkeypatch.setitem(sys.modules, "jeeves_settings", mock.Mock(apply_file_settings=lambda p: None))
    monkeypatch.setitem(sys.modules, "crash_report", mock.Mock(install=lambda n: None))

    rc = jeeves_main.main(
        ["--chair", "--http", "127.0.0.1:17700", "--home", str(home)]
    )
    assert rc == 1
    locks.release_instance_mutex.assert_called()