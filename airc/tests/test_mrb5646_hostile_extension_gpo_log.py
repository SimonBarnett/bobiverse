"""Hostile pins for MRB #5646 / FR #5644 EXTENSION GPO log + DONE exit."""
from __future__ import annotations

import airc_extension as ex


def test_mrb5646_gpo_step_skipped_does_not_add_gpo_failure():
    """attempted=False (fill-holes-only) must not invent step=gpo in failures[]."""
    log = ex.extension_log_from_payload(
        "install",
        whatif=False,
        payload={
            "ok": True,
            "hosts": [{"host": "H1", "ok": True}],
            # no gpo / gpo_detail => gpo_step_skipped attempted=False
        },
    )
    assert log["gpo"].get("attempted") is False
    assert log["gpo"].get("reason") == "gpo_step_skipped"
    assert not any(f.get("step") == "gpo" for f in (log.get("failures") or []))


def test_mrb5646_does_not_double_append_gpo_failure():
    payload = {
        "ok": False,
        "gpo_detail": {
            "ok": False,
            "reason": "gpo_remote_failed",
            "error": "Access is denied.",
            "dc": "WALRUS.wonderland.local",
            "gpo_via": "invoke_command_dc",
            "wrote_gpo": False,
        },
        "failures": [
            {
                "step": "gpo",
                "error": "Access is denied.",
                "dc": "WALRUS.wonderland.local",
            }
        ],
        "hosts": [],
    }
    log = ex.extension_log_from_payload("install", whatif=False, payload=payload)
    gpo_fails = [f for f in log["failures"] if f.get("step") == "gpo"]
    assert len(gpo_fails) == 1


def test_mrb5646_format_keeps_exit_code_when_present():
    block = ex._format_gpo_log_block(
        {
            "ok": False,
            "reason": "gpo_remote_failed",
            "error": "Access is denied.",
            "dc": "DC1",
            "gpo_via": "invoke_command_dc",
            "exit_code": 5,
            "wrote_gpo": False,
            "browsers": [],
            "policy_names": [],
        }
    )
    assert block.get("exit_code") == 5
    assert "Access is denied" in (block.get("error") or "")


def test_mrb5646_skill_row_names_fr5644():
    from pathlib import Path
    from repo_layout import ROOT

    skill = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "FR #5644" in text
    assert "gpo_via" in text
    assert "exit=1" in text or "failure_count" in text
    assert not skill.read_bytes().startswith(bytes([0xEF, 0xBB, 0xBF]))
