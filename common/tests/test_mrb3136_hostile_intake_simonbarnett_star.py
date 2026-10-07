"""MRB #3136 hostile pins: FR #3135 SimonBarnett/* intake owner gate."""
from __future__ import annotations

from pathlib import Path

import intake

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
PLAN = (
    ROOT
    / "bob"
    / "agents"
    / "plan"
    / ".grok"
    / "skills"
    / "plan-git-from-plan"
    / "SKILL.md"
)
MONITOR = ROOT / "jeeves" / "tools" / "monitor" / "intake_allowlist.py"
WEBHOOKS = ROOT / "jeeves" / "docs" / "webhooks.md"


def test_mrb3136_repo_allowed_case_insensitive_owner():
    assert intake.repo_allowed("simonbarnett/Any-New-Product") is True
    assert intake.repo_allowed("SimonBarnett/foo-bar") is True


def test_mrb3136_repo_denied_other_org_and_malformed():
    assert intake.repo_allowed("evil/x") is False
    assert intake.repo_allowed("OtherOrg/bobiverse") is False
    assert intake.repo_allowed("") is False
    assert intake.repo_allowed("nopath") is False


def test_mrb3136_validate_and_outbox_mirror_gate():
    err, norm = intake.validate_payload(
        {
            "repo": "SimonBarnett/brand-new-plan",
            "kind": "fr",
            "title": "scaffold",
            "body": "plan",
        }
    )
    assert err is None
    assert norm["repo"] == "SimonBarnett/brand-new-plan"
    assert (
        intake.outbox_drop_reason({"repo": "SimonBarnett/brand-new-plan", "title": "t"})
        is None
    )
    assert intake.outbox_drop_reason({"repo": "evil/x", "title": "t"}) == "repo_not_allowed"


def test_mrb3136_harvest_skill_documents_owner_gate_not_per_repo_churn():
    raw = HARVEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "Test-IntakeRepoAllowed" in text or "repo_allowed" in text
    assert "3135" in text
    assert "SimonBarnett/" in text
    # Must not still tell operators to add every new product to DEFAULT_ALLOW_REPOS.
    assert "To allow a new product repo, add it to `DEFAULT_ALLOW_REPOS`" not in text


def test_mrb3136_plan_git_and_webhooks_pin_3135():
    plan = PLAN.read_text(encoding="utf-8")
    assert "3135" in plan
    assert "SimonBarnett/" in plan
    assert "no per-repo" in plan.lower()
    doc = WEBHOOKS.read_text(encoding="utf-8-sig")
    assert "3135" in doc
    assert "SimonBarnett/" in doc


def test_mrb3136_monitor_remediation_names_owner_gate():
    text = MONITOR.read_text(encoding="utf-8")
    assert "repo_allowed" in text
    assert "3135" in text
    assert "owner gate" in text.lower() or "SimonBarnett" in text
    assert "picks up the allow rule" in text or "allow rule" in text


def test_mrb3136_harvest_ps1_has_test_intake_repo_allowed():
    text = (SCRIPTS / "Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8-sig")
    assert "function Test-IntakeRepoAllowed" in text
    assert "3135" in text
