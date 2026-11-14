"""MRB #7358 hostile: Autoload=All on every WinPS child path (incl. import-fail)."""
from __future__ import annotations

import bob_worker as bw
import winps51


def test_mrb7358_apply_forces_all_over_none():
    env = {"PSModuleAutoLoadingPreference": "None", "PSModulePath": "C:\\bogus"}
    winps51.apply_winps51_module_path(env)
    assert env["PSModuleAutoLoadingPreference"] == "All"
    assert env["PSModulePath"] == winps51.WINPS51_MODULE_PATH


def test_mrb7358_prepare_seat_fallback_sets_autoload(monkeypatch):
    """When winps51 import fails, seat env still gets Autoload=All (not bare ModulePath)."""
    import builtins

    real_import = builtins.__import__

    def boom(name, *a, **k):
        if name == "winps51" or name.startswith("winps51."):
            raise ImportError("hostile")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", boom)
    out = bw.prepare_seat_child_env({"PSModuleAutoLoadingPreference": "None"})
    assert out.get("PSModuleAutoLoadingPreference") == "All"
    assert "WindowsPowerShell\\v1.0\\Modules" in (out.get("PSModulePath") or "")
