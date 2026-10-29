"""FR #4990: priority-customer repos default to harvest-agent-skills (not common/harvest).

rees/lynton/trutex/euroflo must park at repo-root harvest-agent-skills when -Book is
default harvest (class of orphan rees tips under common/.grok/skills/harvest).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"

PRIORITY_CUSTOMERS = (
    "SimonBarnett/rees",
    "SimonBarnett/lynton",
    "SimonBarnett/trutex",
    "SimonBarnett/euroflo",
)


def _dry_run(repo: str, lesson: str) -> tuple[dict | None, str]:
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HARVEST_PS1),
        "-Repo",
        repo,
        "-Summary",
        f"FR4990 {repo} pin",
        "-Lesson",
        lesson,
        "-DryRun",
    ]
    run = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(ROOT),
        env=os.environ.copy(),
    )
    text = (run.stdout or "") + "\n" + (run.stderr or "")
    assert run.returncode == 0, text[-3000:]
    start, end = text.find("{"), text.rfind("}")
    payload = None
    if start >= 0 and end > start:
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            payload = None
    return payload, text


def test_fr4990_product_default_uses_generic_customer_honesty_box():
    for repo in PRIORITY_CUSTOMERS:
        key = repo.lower()
        assert key not in intake.PRODUCT_DEFAULT_SKILL_BOOK
        book, path = intake.product_default_skill_book(repo, topic_repos=set())
        assert book == "harvest-agent-skills"
        assert path.replace("\\", "/") == ".grok/skills/harvest-agent-skills/SKILL.md"


def test_fr4990_resolve_skill_book_priority_customers_empty_topics():
    for repo in PRIORITY_CUSTOMERS:
        book, path = intake.resolve_skill_book(
            skill_book="harvest",
            title=f"harvest: {repo} tip",
            body="customer service-call playbook",
            repo=repo,
            topic_repos=set(),
        )
        assert book == "harvest-agent-skills", repo
        assert path.replace("\\", "/") == ".grok/skills/harvest-agent-skills/SKILL.md"
        assert "common/.grok/skills/harvest/" not in path.replace("\\", "/")


def test_fr4990_harvest_ps1_priority_customer_branch():
    text = HARVEST_PS1.read_text(encoding="utf-8")
    assert "FR #4990" in text
    assert "euroflo|lynton|trutex|rees" in text or (
        "lynton" in text and "trutex" in text and "rees" in text
    )


def test_fr4990_dryrun_rees_emits_harvest_agent_skills():
    lesson = (
        "FR4990 rees DryRun pin --- never common/.grok/skills/harvest for "
        "SimonBarnett/rees priority-customer honesty box"
    )
    payload, text = _dry_run("SimonBarnett/rees", lesson)
    assert "harvest-agent-skills" in text
    assert "common/.grok/skills/harvest/SKILL.md" not in text or (
        "skill_book=harvest-agent-skills" in text
        or (payload and payload.get("source", {}).get("skill_book") == "harvest-agent-skills")
    )
    if payload:
        assert payload["repo"] == "SimonBarnett/rees"
        assert (payload.get("source") or {}).get("skill_book") == "harvest-agent-skills"
        path = (payload.get("source") or {}).get("skill_book_path") or payload.get(
            "skill_book_path"
        )
        assert path and "harvest-agent-skills" in str(path)
        assert "common/.grok/skills/harvest/SKILL.md" not in str(path)
