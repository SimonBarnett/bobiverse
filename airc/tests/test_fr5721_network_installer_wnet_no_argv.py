"""FR #5721: network installer _net_use must not put password on net use argv."""
from __future__ import annotations

from types import SimpleNamespace

import airc_wnet
from airc_network_installer import install as inst


def test_fr5721_net_use_source_has_no_password_argv():
    from pathlib import Path
    from repo_layout import ROOT

    src = (ROOT / "airc/scripts/airc_network_installer/install.py").read_text(
        encoding="utf-8"
    )
    # Pin: must not extend cmd with password for net use (FR #5709 class).
    assert 'cmd.extend([f"/user:{username}", password])' not in src
    assert "wnet_add" in src or "airc_wnet" in src
    assert "FAKE_" not in src  # no secret literals in product


def test_fr5721_net_use_calls_wnet_not_subprocess(monkeypatch):
    runs: list = []
    added: list = []

    def fake_run(*a, **k):
        cmd = a[0] if a else k.get("args")
        runs.append(list(cmd) if cmd is not None else [])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_add(remote, username, password):
        added.append((remote, username, password))
        return remote

    monkeypatch.setattr(inst.subprocess, "run", fake_run)
    monkeypatch.setattr(inst, "wnet_add", fake_add)
    inst._net_use(r"\\REDQUEEN\IPC$", r"WONDERLAND\Administrator", "FAKE_secret")
    assert added == [(r"\\REDQUEEN\IPC$", r"WONDERLAND\Administrator", "FAKE_secret")]
    # No net.exe invocation with the secret on argv.
    for cmd in runs:
        blob = " ".join(str(x) for x in cmd)
        assert "FAKE_secret" not in blob
        assert not (len(cmd) >= 2 and str(cmd[0]).lower().endswith("net") and "use" in [str(x).lower() for x in cmd])


def test_fr5721_net_use_delete_calls_wnet_cancel(monkeypatch):
    cancelled: list = []
    runs: list = []

    monkeypatch.setattr(inst, "wnet_cancel", lambda remote: cancelled.append(remote))
    monkeypatch.setattr(
        inst.subprocess,
        "run",
        lambda *a, **k: runs.append(a[0] if a else None)
        or SimpleNamespace(returncode=0),
    )
    inst._net_use_delete(r"\\REDQUEEN\IPC$")
    assert cancelled == [r"\\REDQUEEN\IPC$"]
    for cmd in runs:
        if cmd is None:
            continue
        blob = " ".join(str(x) for x in cmd)
        assert "FAKE_secret" not in blob


def test_fr5721_wnet_add_raises_real_winerror(monkeypatch):
    import ctypes

    class _Fn:
        argtypes = None
        restype = None

        def __call__(self, *a, **k):
            return 53

    class Boom:
        WNetAddConnection2W = _Fn()

    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: Boom())
    try:
        airc_wnet.wnet_add(r"\\NOPE\IPC$", "u", "FAKE_pw")
        assert False, "expected OSError"
    except OSError as exc:
        code = int(getattr(exc, "winerror", 0) or getattr(exc, "errno", 0) or 0)
        assert code == 53
        assert "FAKE_pw" not in str(exc)
