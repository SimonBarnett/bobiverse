"""a-search harvests landed in SimonBarnett/bobiverse (2026-10-08).

Root cause: bob_worker wrote job-repo.txt from the typed ACK key
("FR SimonBarnett/a-search#637"); harvest_repo_for_job could not parse the
"FR " prefix and fell back to SimonBarnett/bobiverse, and
Invoke-BobiverseHarvest.ps1 defaulted -Repo to bobiverse when nothing was set.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
import bob_worker as bw  # noqa: E402

HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"


@pytest.mark.parametrize(
    "key",
    [
        "FR SimonBarnett/a-search#637",
        "MRB SimonBarnett/a-search#723",
        "ACK UAT SimonBarnett/a-search#9",
        "https://github.com/SimonBarnett/a-search/pull/728",
        "SimonBarnett/a-search#5",
    ],
)
def test_typed_job_keys_map_to_a_search(key):
    assert bw.harvest_repo_for_job(key) == "SimonBarnett/a-search"
    assert bw.parse_job_repo(key) == "SimonBarnett/a-search"


def test_outbox_ack_key_round_trip_writes_a_search_marker(tmp_path: Path):
    key = bw.outbox_job_key("ACK FR SimonBarnett/a-search#637")
    assert key == "FR SimonBarnett/a-search#637"
    assert bw.write_job_repo_marker(tmp_path, key) == "SimonBarnett/a-search"
    assert (tmp_path / "job-repo.txt").read_text(encoding="utf-8").strip() == "SimonBarnett/a-search"
    assert bw.write_job_repo_marker(tmp_path, "MRB SimonBarnett/bobiverse#3329") == "SimonBarnett/bobiverse"


def test_unreadable_job_key_removes_marker_instead_of_bobiverse(tmp_path: Path):
    (tmp_path / "job-repo.txt").write_text("SimonBarnett/a-search\n", encoding="utf-8")
    assert bw.write_job_repo_marker(tmp_path, "garbage") == ""
    assert not (tmp_path / "job-repo.txt").exists()


def test_worker_prompt_demands_explicit_job_repo():
    text = bw.worker_prompt(r"C:\worker", r"C:\home", "testbox", "testbox-1")
    assert "-Repo <owner/repo from the job id>" in text
    assert "a-search lessons must never go to SimonBarnett/bobiverse" in text


@pytest.mark.parametrize(
    "rel",
    [
        "bob/agents/worker/AGENTS.md",
        "bob/agents/worker/.grok/skills/bobiverse-worker-seat/SKILL.md",
        "common/.grok/skills/harvest/SKILL.md",
    ],
)
def test_seat_skills_pin_harvest_repo(rel):
    text = (ROOT / rel).read_text(encoding="utf-8-sig")
    assert "Invoke-BobiverseHarvest.ps1 -Repo <owner/repo of the job>" in text
    assert "Never harvest a-search or other product lessons to" in text


def _ps() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


def _dry(env_extra: dict, summary: str, lesson: str):
    exe = _ps()
    args = [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HARVEST_PS1),
            "-Summary", summary, "-Lesson", lesson, "-DryRun"]
    env = {k: v for k, v in os.environ.items() if k not in ("BOB_JOB_REPO", "BOB_OUTBOX")}
    env.update(env_extra)
    return subprocess.run(args, capture_output=True, text=True, timeout=60, env=env, cwd=str(ROOT))


def _payload(run) -> dict:
    text = (run.stdout or "") + "\n" + (run.stderr or "")
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


@pytest.mark.skipif(_ps() is None, reason="needs PowerShell")
def test_ps1_typed_marker_routes_to_a_search(tmp_path: Path):
    (tmp_path / "job-repo.txt").write_text("FR SimonBarnett/a-search#637\n", encoding="utf-8")
    run = _dry({"BOB_OUTBOX": str(tmp_path / "outbox.txt")}, "FR-084 partnerize selftest", "selftestProbe stays dark")
    assert run.returncode == 0, run.stdout + run.stderr
    p = _payload(run)
    assert p["repo"] == "SimonBarnett/a-search"
    assert p["source"]["skill_book"] == "harvest-agent-skills"


@pytest.mark.skipif(_ps() is None, reason="needs PowerShell")
def test_ps1_no_repo_a_search_lesson_goes_to_a_search(tmp_path: Path):
    run = _dry({}, "MRB a-search#723 PASS", "a-search Phase-2 selftest MRB: merge behind-main tip first")
    assert run.returncode == 0, run.stdout + run.stderr
    assert _payload(run)["repo"] == "SimonBarnett/a-search"


@pytest.mark.skipif(_ps() is None, reason="needs PowerShell")
def test_ps1_seat_without_repo_or_owner_refuses(tmp_path: Path):
    run = _dry({"BOB_OUTBOX": str(tmp_path / "outbox.txt")}, "FR-099 stay dark", "keep enabled false")
    assert run.returncode != 0
    assert "pass -Repo" in (run.stdout + run.stderr)
