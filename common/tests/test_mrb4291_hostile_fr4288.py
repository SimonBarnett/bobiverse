"""Hostile pins for MRB #4291 / FR #4288 ExistingPrUrl tip-loop fail-closed."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import intake  # noqa: E402

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"
SKILL = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
PRODUCT_PR = "https://github.com/SimonBarnett/a-search/pull/2195"


def _run(*extra: str) -> subprocess.CompletedProcess[str]:
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


def test_mrb4291_skill_contiguous_fr4288_and_3189():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4288" in text
    needle = (
        "-ExistingPrUrl (or a pull URL in Summary/Lesson) fail-closes tip filing"
    )
    assert needle in text
    assert "FR #3189" in text
    # Preserve product routing phrase near FR #4288 bullet
    idx = text.index("FR #4288")
    window = text[idx : idx + 280]
    assert "harvest-agent-skills" in window
    assert "do not redirect product playbooks to bobiverse harvest" in window


def test_mrb4291_client_skips_existing_pr_param(tmp_path: Path):
    r = _run(
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "MRB hostile: tip-loop must skip",
        "-Lesson",
        "ExistingPrUrl fail-closes second lesson tip",
        "-ExistingPrUrl",
        PRODUCT_PR,
        "-OutboxDir",
        str(tmp_path / "out"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest ExistingPrUrl tip-loop (FR #4288" in r.stdout
    assert "SKIPPED harvest lesson-review loop" not in r.stdout
    assert "HARVESTED" not in r.stdout


def test_fr5483_existing_pr_skip_before_lesson_review():
    src = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
    text = src.read_text(encoding="utf-8-sig")
    i4288 = text.find("SKIPPED harvest ExistingPrUrl tip-loop")
    i4780 = text.find("SKIPPED harvest lesson-review loop")
    assert i4288 >= 0 and i4780 >= 0
    assert i4288 < i4780
    assert "FR #5483" in text


def test_mrb4291_intake_existing_pr_wins_before_tip(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.files = {".grok/skills/harvest-agent-skills/SKILL.md": "# book\n\n"}
    home = tmp_path / "home"
    home.mkdir()
    norm = {
        "kind": "harvest",
        "repo": "SimonBarnett/a-search",
        "title": "harvest: with Existing PR cite",
        "body": (
            "Session summary:\nx\n\nLessons:\n- playbook line\n\n"
            f"Existing PR: {PRODUCT_PR}\n"
        ),
        "files": [{"path": "x.md", "content": "y"}],
        "source": {
            "machine": "marchhare",
            "agent": "Invoke-BobiverseHarvest",
            "skill_book": "harvest-agent-skills",
            "version": "",
        },
        "idempotency_key": "hv-mrb4291-1",
        "contact": "",
        "contact_public": False,
    }
    rec = intake.file_submission(home, norm, filer, intake_id="in_mrb4291")
    assert rec["state"] == "linked_existing_pr"
    assert rec["number"] == 2195
    assert filer.prs == []
    assert filer.issues == []


def test_mrb4291_utf8_no_bom_skill_and_tests():
    for rel in (
        SKILL,
        ROOT / "common" / "tests" / "test_fr4288_harvest_existing_pr_skip_tip.py",
    ):
        raw = rel.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), rel
        assert b"<<<<<<<" not in raw
