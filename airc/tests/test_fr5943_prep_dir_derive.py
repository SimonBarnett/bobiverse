"""FR #5943: PRIORITY prepare derives prep folder; prepDir is optional override."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from repo_layout import ROOT

_WP = ROOT / "airc" / "priority-worker"
if str(_WP) not in sys.path:
    sys.path.insert(0, str(_WP))

import priority_worker as pw  # noqa: E402

BASE = {
    "id": "hrs-dev-live1",
    "url": "https://prioritydev.example.invalid",
    "company": "live1",
    "user": "api-user",
    "credentialTarget": "PriorityWeb/hrs-dev-live1",
    "sqlServer": ".\\PRI",
    "systemDb": "system",
}


def _ok_hooks(**over):
    h = {
        "cred_present": lambda target: True,
        "sdk_exec": lambda **kw: {"ok": True, "path": "REPPREPDIRECT2"},
        "read_upd": lambda **kw: "N",
        "prp_mtime_before": 100.0,
        "prp_mtime_after": lambda **kw: 200.0,
        "proc_type": "P",
    }
    h.update(over)
    return h


def test_fr5943_derived_from_priority_root_when_no_prep_dir(tmp_path):
    prep = tmp_path / "priority" / "system" / "prep"
    prep.mkdir(parents=True)
    inst = dict(BASE)
    inst["priorityRoot"] = str(tmp_path / "priority")
    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[inst],
        **_ok_hooks(),
    )
    assert r["ok"] is True
    assert r["reason"] == "prepared"
    assert Path(r["prep_dir"]) == prep
    assert r["prep_dir_source"] == "derived"
    assert "priority_root" in (r.get("prep_dir_tried") or [])


def test_fr5943_override_wins_over_derivation(tmp_path):
    derived = tmp_path / "priority" / "system" / "prep"
    derived.mkdir(parents=True)
    override = tmp_path / "override_prep"
    override.mkdir()
    inst = dict(BASE)
    inst["priorityRoot"] = str(tmp_path / "priority")
    inst["prepDir"] = str(override)
    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[inst],
        **_ok_hooks(),
    )
    assert r["ok"] is True
    assert Path(r["prep_dir"]) == override
    assert r["prep_dir_source"] == "override"


def test_fr5943_derivation_fail_reports_tried_sources(monkeypatch):
    # Isolate from host tabula.ini / PRIORITY_* so the fail path is deterministic.
    monkeypatch.delenv("PRIORITY_PREP_DIR", raising=False)
    monkeypatch.delenv("PRIORITY_ROOT", raising=False)
    monkeypatch.delenv("PRIORITY_HOME", raising=False)
    monkeypatch.setattr(pw, "_read_tabula_ini_prep_dir", lambda **_k: None)
    inst = dict(BASE)  # no prepDir, no priorityRoot
    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[inst],
        **_ok_hooks(),
    )
    assert r["ok"] is False
    assert r["reason"] == "prep_dir_missing"
    tried = r.get("prep_dir_tried") or []
    assert isinstance(tried, list) and len(tried) >= 1
    assert "override" in tried or "priority_root" in tried
    assert r.get("prep_dir_source") in (None, "", "none")


def test_fr5943_invalid_override_fails_closed_no_fallthrough(tmp_path):
    """Explicit bad prepDir must not fall through to a valid derived path."""
    derived = tmp_path / "priority" / "system" / "prep"
    derived.mkdir(parents=True)
    bad = tmp_path / "missing_override"
    inst = dict(BASE)
    inst["priorityRoot"] = str(tmp_path / "priority")
    inst["prepDir"] = str(bad)
    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[inst],
        **_ok_hooks(),
    )
    assert r["ok"] is False
    assert r["reason"] == "prep_dir_missing"
    assert (r.get("prep_dir_tried") or []) == ["override"]
    assert Path(r.get("prep_dir") or "") != derived


def test_fr5943_tabula_ini_derives_prep(tmp_path, monkeypatch):
    prep = tmp_path / "priority" / "system" / "prep"
    prep.mkdir(parents=True)
    windir = tmp_path / "Windows"
    windir.mkdir()
    (windir / "tabula.ini").write_text(
        "[Tabula]\nPriority Directory={0}\n".format(prep),
        encoding="utf-8",
    )
    monkeypatch.setenv("WINDIR", str(windir))
    monkeypatch.delenv("PRIORITY_PREP_DIR", raising=False)
    monkeypatch.delenv("PRIORITY_ROOT", raising=False)
    inst = dict(BASE)
    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[inst],
        **_ok_hooks(),
    )
    assert r["ok"] is True
    assert Path(r["prep_dir"]) == prep
    assert r["prep_dir_source"] == "derived"
    assert "tabula_ini" in (r.get("prep_dir_tried") or [])


def test_fr5943_docs_skill_say_prepdir_optional():
    doc = (ROOT / "airc" / "docs" / "airc-priority-client.md").read_text(encoding="utf-8")
    assert "optional" in doc.lower() and "prepDir" in doc
    assert "required for `PRIORITY prepare`" not in doc
    assert "prep_dir_missing" in doc
    skill = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "optional" in skill.lower() or "override" in skill.lower()
    assert "5943" in skill
