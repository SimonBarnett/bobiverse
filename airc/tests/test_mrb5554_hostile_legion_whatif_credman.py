"""docs/mrb-5554: hostile pins for LEGION WhatIf without CredMan (FR #5530)."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg
from repo_layout import ROOT


def test_mrb5554_skill_whatif_credman_missing_phrase():
    skill = (ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(encoding="utf-8")
    window = skill[skill.index("## LEGION remote install") : skill.index("## LEGION remote install") + 1200]
    assert "FR #5530" in window
    assert "credman-missing" in window or "FR #5659" in window or "falls through" in window.lower()
    assert "WhatIf" in window
    assert "auth_failed" in window or "fail-closes" in window or "fail-closed" in window or "FR #5659" in window


def test_mrb5554_whatif_plans_without_secret():
    seen = []

    def run_fn(spec):
        seen.append(spec)
        return {"ok": True, "status": "dry-run", "msi": "latest", "psexec": r"C:\Tools\PsExec.exe"}

    body = lg.installer_legion_work("flamingo", whatif=True, run_fn=run_fn, credman=lambda: {})
    assert seen and body["invoked_installer"] is True
    assert body.get("credman_missing") is True or any(f.get("error") == "credman-missing" for f in (body.get("failures") or []))
    assert body.get("status") == "dry-run"


def test_mrb5554_live_falls_through_to_system():
    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=lambda s: {"ok": True, "status": "ok"},
        credman=lambda: {},
    )
    assert body["invoked_installer"] is True
    assert body.get("credman_missing") is True
    assert body.get("identity") == "system"
