"""MRB #5342 hostile pins: FR #5288 client remaining includes Priority module."""
from __future__ import annotations

from repo_layout import ROOT

ALLOW = ROOT / "airc/tests/test_fr3514_client_allowlist_payload.py"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
PRIO = ROOT / "airc/docs/airc-priority-client.md"


def test_mrb5342_remaining_has_module_and_worker():
    t = ALLOW.read_text(encoding="utf-8")
    assert "len(CLIENT_REMAINING_FILES) == 33" in t
    assert r"scripts\airc_priority.py" in t
    assert r"airc\priority-worker\priority_worker.py" in t
    allow = COMMON.read_text(encoding="utf-8-sig")
    fn = allow[
        allow.index("function Get-BobiverseAircClientAllowedScriptNames") : allow.index(
            "function Get-BobiverseAircMsiAgentLayerScriptNames"
        )
    ]
    assert "airc_priority.py" in fn
    assert "airc_jobs.py" in fn


def test_mrb5342_docs_default_on_not_feature():
    text = PRIO.read_text(encoding="utf-8")
    assert "5288" in text
    assert "default" in text.lower()
    assert "not a separate" in text.lower()
    assert "PriorityClient.exe" not in text
