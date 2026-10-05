"""FR #2522: jeeves.exe --self-test picks up check_<name>.py plugins (jeeves/checks registry)."""
from __future__ import annotations

import json
from pathlib import Path

from repo_layout import ROOT

import jeeves_checks
import jeeves_main

BUILD = ROOT / "jeeves/scripts/Build-Jeeves.ps1"

PROBE = '''
CHECK_NAME = "fr2522_probe"

def run(home, chair_home):
    return {"ok": False, "home": str(home)}, ["fr2522 probe finding"], []
'''

OPT_IN = '''
CHECK_NAME = "fr2522_optin"
INCLUDE_IN_DEFAULT = False

def run(home, chair_home):
    return {"ok": True}, [], []
'''


def _run(capsys, home: Path, checks=None) -> tuple[int, dict]:
    code = jeeves_main.run_self_test(home=home, as_json=True, checks=checks)
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return code, json.loads(out)


def test_fr2522_new_check_picked_up_by_self_test(tmp_path, monkeypatch, capsys):
    plug = tmp_path / "checks"
    plug.mkdir()
    (plug / "check_fr2522_probe.py").write_text(PROBE, encoding="utf-8")
    (plug / "check_fr2522_optin.py").write_text(OPT_IN, encoding="utf-8")
    monkeypatch.setenv("JEEVES_CHECKS_DIR", str(plug))
    monkeypatch.setattr(jeeves_main, "DEFAULT_SELF_TEST", ())  # only plugins, no live box probes
    code, payload = _run(capsys, tmp_path)
    assert "fr2522_probe" in payload["checks"]
    assert "fr2522 probe finding" in payload["findings"]
    assert "fr2522_optin" not in payload["checks"]  # INCLUDE_IN_DEFAULT False
    assert code == 1 and payload["exit"] == 1


def test_fr2522_plugin_runs_by_name(tmp_path, monkeypatch, capsys):
    plug = tmp_path / "checks"
    plug.mkdir()
    (plug / "check_fr2522_optin.py").write_text(OPT_IN, encoding="utf-8")
    monkeypatch.setenv("JEEVES_CHECKS_DIR", str(plug))
    code, payload = _run(capsys, tmp_path, checks=["fr2522_optin"])
    assert code == 0 and payload["checks"]["fr2522_optin"] == {"ok": True}


def test_fr2522_unknown_check_still_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("JEEVES_CHECKS_DIR", str(tmp_path / "nope"))
    code, payload = _run(capsys, tmp_path, checks=["does_not_exist"])
    assert code == 2 and "unknown_check:does_not_exist" in payload["errors"]


def test_fr2522_broken_or_shadowing_plugin_is_error_not_crash(tmp_path, monkeypatch, capsys):
    plug = tmp_path / "checks"
    plug.mkdir()
    (plug / "check_broken.py").write_text("raise RuntimeError('x')\n", encoding="utf-8")
    (plug / "check_locks.py").write_text("CHECK_NAME='locks'\ndef run(h,c):\n    return {}, [], []\n", encoding="utf-8")
    monkeypatch.setenv("JEEVES_CHECKS_DIR", str(plug))
    monkeypatch.setattr(jeeves_main, "DEFAULT_SELF_TEST", ())
    code, payload = _run(capsys, tmp_path)
    assert code == 2
    assert any(e.startswith("plugin_load:check_broken.py") for e in payload["errors"])
    assert "plugin_shadows_builtin:locks" in payload["errors"]


def test_fr2522_registry_searches_repo_checks_folder():
    dirs = [str(d).replace("\\", "/").lower() for d in jeeves_checks.checks_dirs()]
    assert any(d.endswith("jeeves/checks") for d in dirs)
    assert (ROOT / "jeeves/checks/README.md").is_file()


def test_fr2522_build_bundles_checks():
    t = BUILD.read_text(encoding="utf-8")
    assert "'jeeves_checks'" in t
    assert "--add-data" in t and "jeeves\\checks" in t
