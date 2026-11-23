"""FR #9242: MemoryError during heavy jeeves import retries once then exits 1."""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
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

    # FR #9291: main() assigns BOB_DIGEST_HOME / BOB_HOME for the chair process.
    # monkeypatch.delenv(..., raising=False) is a no-op when the key is absent and
    # does not register undo — so a later raw os.environ[...] = leaked into the
    # suite (webhooks 403 not-on-roster, queue append into live digest home).
    # setenv first so undo always clears/restores after the test.
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    monkeypatch.setenv("BOB_HOME", str(home))

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
    # Chair path sets DIGEST_HOME for the process lifetime; monkeypatch.delenv above
    # restores/clears it when this test ends (FR #9291).
    assert os.environ.get("BOB_DIGEST_HOME") == str(home)


def test_fr9291_no_digest_home_leak_after_main_oom_path():
    """Collection-ordered: after test_main_returns_1_when_irc_agent_oom, env is clean.

    Without monkeypatch.delenv on BOB_DIGEST_HOME, fleet_digest_home redirected
    later webhooks/queue tests into the deleted pytest tmp and returned 403/empty.
    """
    leaked = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
    if leaked:
        norm = leaked.replace("\\", "/").lower()
        assert "pytest" not in norm, (
            f"BOB_DIGEST_HOME leaked from prior jeeves_main.main: {leaked!r}"
        )

    import bobcallback
    import bobreport
    import registered_machines as rm

    home = Path(tempfile.mkdtemp())
    rm.sync_from_chanserv(home, ["#bobiverse", "#marchhare"])
    assert "marchhare" in bobreport.roster_machine_ids(home)
    code, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"Content-Type": "application/json"},
        json.dumps({"op": "merge", "machine": "marchhare", "weekly": 1}).encode(),
        "127.0.0.1",
        home,
        {"127.0.0.1"},
    )
    assert code in (200, 204), code
