"""FR #4288: ExistingPrUrl / cited product PR fail-closes tip filing (no tip-loop PR).

Product -Repo -> harvest-agent-skills remains intentional (FR #3189). Tip-loops of an
already-open product PR must not open a second lesson(harvest-agent-skills) tip.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import intake  # noqa: E402

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"
PRODUCT_PR = "https://github.com/SimonBarnett/a-search/pull/2195"


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            *extra,
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
    )


def test_fr4288_script_documents_existing_pr_skip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #4288" in text
    assert "SKIPPED harvest ExistingPrUrl" in text
    assert "3189" in text  # must not undo product routing


def test_fr4288_skips_when_existing_pr_url_param(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "FR-248 outbound networkParams; PR opened",
        "-Lesson",
        "FR-248 outbound: buildTrackedUrl -> buildOutboundUrl; merchant plain URL",
        "-ExistingPrUrl",
        PRODUCT_PR,
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest ExistingPrUrl" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    out = tmp_path / "harvest-outbox"
    assert not list(out.glob("*.json")) if out.exists() else True


def test_fr4288_skips_when_summary_cites_product_pr(tmp_path: Path):
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        f"FR-248 done; Existing PR: {PRODUCT_PR}",
        "-Lesson",
        "FR-248 outbound: buildTrackedUrl -> buildOutboundUrl",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest ExistingPrUrl" in r.stdout
    assert "HARVESTED" not in r.stdout


def test_fr4288_product_repo_still_defaults_harvest_agent_skills_dryrun():
    """FR #3189 must survive: a-search job harvest still targets harvest-agent-skills."""
    r = _run_harvest(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "new Squarespace vault playbook from FR-242 MRB",
        "-Lesson",
        "Squarespace short-lived accessToken in vault for first sync is ACCEPTABLE drift",
        "-DryRun",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest ExistingPrUrl" not in r.stdout
    assert "harvest-agent-skills" in r.stdout
    assert "SimonBarnett/a-search" in r.stdout


def test_fr4288_intake_links_existing_pr_even_with_lessons(tmp_path: Path):
    """Intake must prefer linked_existing_pr over lesson tip when a PR URL is cited."""
    filer = intake.FakeGitHubFiler()
    filer.files = {".grok/skills/harvest-agent-skills/SKILL.md": "# harvest-agent-skills\n\n"}
    home = tmp_path / "intake_home"
    home.mkdir()
    norm = {
        "kind": "harvest",
        "repo": "SimonBarnett/a-search",
        "title": "harvest: FR-248 outbound; PR opened",
        "body": (
            "Session summary:\nFR-248\n\nLessons:\n- buildOutboundUrl\n\n"
            f"Existing PR: {PRODUCT_PR}\n"
        ),
        "files": [],
        "source": {
            "machine": "marchhare",
            "agent": "Invoke-BobiverseHarvest",
            "skill_book": "harvest-agent-skills",
            "version": "",
        },
        "idempotency_key": "hv-fr4288-link1",
        "contact": "",
        "contact_public": False,
    }
    rec = intake.file_submission(home, norm, filer, intake_id="in_fr4288a")
    assert rec["state"] == "linked_existing_pr"
    assert rec["number"] == 2195
    assert "pull/2195" in rec["url"]
    assert filer.issues == []
    assert filer.prs == []
