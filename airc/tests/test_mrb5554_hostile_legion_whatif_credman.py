"""docs/mrb-5554: hostile pins for LEGION WhatIf without CredMan (FR #5530)."""
from __future__ import annotations

from pathlib import Path

import airc_legion as lg
from repo_layout import ROOT


def test_mrb5554_skill_whatif_credman_missing_phrase():
    skill = (ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(encoding="utf-8")
    window = skill[skill.index("## LEGION remote install") : skill.index("## LEGION remote install") + 1200]
    assert "FR #5530" in window
    assert "credman-missing" in window
    assert "WhatIf" in window
    assert "fail-closes" in window or "fail-closed" in window


def test_mrb5554_whatif_plans_without_secret():
    seen = []

    def run_fn(spec):
        seen.append(spec)
        return {"ok": True, "status": "dry-run", "msi": "latest", "psexec": r"C:\Tools\PsExec.exe"}

    body = lg.installer_legion_work("flamingo", whatif=True, run_fn=run_fn, credman=lambda: {})
    assert seen and body["invoked_installer"] is True
    assert any(f.get("error") == "credman-missing" for f in (body.get("failures") or []))
    assert body.get("status") == "dry-run"


def test_mrb5554_live_still_fail_closed():
    body = lg.installer_legion_work(
        "flamingo",
        whatif=False,
        run_fn=lambda s: (_ for _ in ()).throw(AssertionError("no")),
        credman=lambda: {},
    )
    assert body["invoked_installer"] is False
    assert body["error"] == "credman-missing"
