"""FR #5932: PRIORITY prepare must not report prp_unchanged when prepDir is missing."""
from __future__ import annotations

import json
import sys

from repo_layout import ROOT

_WP = ROOT / "airc" / "priority-worker"
if str(_WP) not in sys.path:
    sys.path.insert(0, str(_WP))

import priority_worker as pw  # noqa: E402

INST_NO_PREP = {
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
        # Without the FR #5932 gate these zeros would look like prp_unchanged.
        "prp_mtime_before": 0.0,
        "prp_mtime_after": lambda **kw: 0.0,
        "proc_type": "P",
    }
    h.update(over)
    return h


def test_fr5932_missing_prep_dir_is_explicit_not_prp_unchanged():
    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[INST_NO_PREP],
        **_ok_hooks(),
    )
    assert r["ok"] is False
    assert r["reason"] == "prep_dir_missing"
    assert r.get("prp_advanced") is False
    assert r.get("prp_mtime_before") == 0.0
    assert r.get("prp_mtime_after") == 0.0
    assert "prp_unchanged" not in json.dumps(r)


def test_fr5932_default_hooks_missing_prep_dir_before_sdk():
    """Live hooks must also fail closed before claiming prp_unchanged."""
    seen = {"sdk": 0}

    def sdk_exec(**_kw):
        seen["sdk"] += 1
        return {"ok": True, "path": "REPPREPDIRECT2"}

    hooks = pw.build_default_prepare_hooks(
        cred_fetcher=lambda _t: "secret" + "-placeholder-" + "prep",
        lock_reader=lambda **_k: {"exec_id": 21848, "upd": "N"},
        sdk_exec=sdk_exec,
        prp_stat=lambda **_k: 0.0,
    )
    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[INST_NO_PREP],
        **hooks,
    )
    assert r["reason"] == "prep_dir_missing"
    assert r["ok"] is False
    # Fail before SDK so we do not pretend prepare ran under unknown prepDir.
    assert seen["sdk"] == 0


def test_fr5932_docs_and_skill_name_prep_dir_missing():
    doc = (ROOT / "airc" / "docs" / "airc-priority-client.md").read_text(encoding="utf-8")
    assert "prep_dir_missing" in doc
    assert "prepDir" in doc
    skill = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "prep_dir_missing" in skill
    assert "5932" in skill

def test_fr5932_nonexistent_prep_dir_is_prep_dir_missing(tmp_path):
    """Hostile (MRB #5934): non-empty missing path must not reach SDK / prp_unchanged."""
    inst = dict(INST_NO_PREP)
    inst["prepDir"] = str(tmp_path / "no-such-prep")
    sdk_calls = {"n": 0}

    def sdk(**kw):
        sdk_calls["n"] += 1
        return {"ok": True, "path": "REPPREPDIRECT2"}

    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[inst],
        **_ok_hooks(sdk_exec=sdk),
    )
    assert r["reason"] == "prep_dir_missing"
    assert sdk_calls["n"] == 0

