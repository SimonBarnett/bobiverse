"""MRB #5944 / FR #5960 gate: prep-dir resolve is lazy; no Priority -> clean refuse."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import airc_fail_intake as fail
import airc_priority as ap
import priority_worker as pw
from airc_auth_helpers import ops_auth
import airc_console as ac


def test_mrb5944_resolve_prep_dir_not_invoked_at_import(monkeypatch):
    """Finding prep must not run at import / service start (Si #5960)."""
    calls = {"n": 0}
    real = pw.resolve_prep_dir

    def _spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(pw, "resolve_prep_dir", _spy)
    # Re-import console / priority modules must not call resolve_prep_dir.
    importlib.reload(ap)
    assert calls["n"] == 0
    # Direct unit resolve is still available when prepare asks.
    r = pw.resolve_prep_dir({})
    assert calls["n"] == 1
    assert r.get("path") == ""
    assert "override" in (r.get("tried") or [])


def test_mrb5944_prepare_without_priority_refuses_clean_no_intake(tmp_path, monkeypatch):
    """PRIORITY prepare on a host with no live allowlist -> priority_not_installed."""
    calls = []
    monkeypatch.setattr(fail, "report_verb_failure", lambda *a, **k: calls.append(1) or None)
    auth = ops_auth("bob-walrus", channel="#walrus")
    root = tmp_path / "airc-install"
    (root / "config").mkdir(parents=True)
    core = ac.AircConsoleCore(
        machine="walrus",
        auth=auth,
        nick="walrus_console",
        install_root=str(root),
    )
    r = core.handle_raw(
        ":bob-walrus!u@h PRIVMSG walrus_console :PRIORITY prepare WWWSHOWCUST"
    )
    assert r is not None
    assert "priority_not_installed" in (r.reply or "")
    assert calls == []
    # Prep resolve helper itself stays fail-closed without raising.
    missing = pw.resolve_prep_dir({"id": "x"})
    assert missing.get("path") == ""
    assert missing.get("source") in ("", None)


def test_mrb5944_priority_runtime_probe_ignores_example_json(tmp_path):
    root = tmp_path / "pkg"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    ex = Path(__file__).resolve().parents[1] / "config" / "priority-instances.example.json"
    (cfg / "priority-instances.example.json").write_text(
        ex.read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert ap.priority_runtime_available(root) is False
    assert ap.priority_absent_reason(root) == "priority_not_installed"
