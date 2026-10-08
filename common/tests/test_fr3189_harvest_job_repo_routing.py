"""FR #3189: product-job harvests target the job repo (a-search), not bobiverse harvest.

Acceptance that fails on pre-3189 main:
- Invoke-BobiverseHarvest -JobRepo SimonBarnett/a-search -DryRun emits repo=a-search
- bob_worker harvest helpers pass -Repo for a-search rows; bobiverse stays bobiverse
- resolve_skill_book(repo=a-search) never returns common/.grok/skills/harvest/SKILL.md
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

import intake

HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
WORKER_PY = ROOT / "bob" / "scripts" / "bob_worker.py"


def _dry_run(*, job_repo: str | None = None, repo: str | None = None, extra_args: list | None = None, env: dict | None = None) -> dict:
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HARVEST_PS1),
        "-Summary",
        "a-search provider Parts query",
        "-Lesson",
        "a-search awin local uses injectable mssql connect",
        "-DryRun",
    ]
    if job_repo:
        args.extend(["-JobRepo", job_repo])
    if repo:
        args.extend(["-Repo", repo])
    if extra_args:
        args.extend(extra_args)
    merged = os.environ.copy()
    if env:
        merged.update({k: str(v) for k, v in env.items()})
    run = subprocess.run(args, capture_output=True, text=True, timeout=60, env=merged, cwd=str(ROOT))
    assert run.returncode == 0, (run.stdout or "") + "\n" + (run.stderr or "")
    text = (run.stdout or "") + "\n" + (run.stderr or "")
    start, end = text.find("{"), text.rfind("}")
    assert start >= 0 and end > start, text[-2000:]
    return json.loads(text[start : end + 1])


def test_fr3189_harvest_dryrun_jobrepo_a_search():
    payload = _dry_run(job_repo="SimonBarnett/a-search")
    assert payload["repo"] == "SimonBarnett/a-search"
    book = (payload.get("source") or {}).get("skill_book") or ""
    assert book == "harvest-agent-skills"
    assert book != "harvest"


def test_fr3189_harvest_dryrun_env_bob_job_repo():
    payload = _dry_run(env={"BOB_JOB_REPO": "SimonBarnett/a-search"})
    assert payload["repo"] == "SimonBarnett/a-search"


def test_fr3189_harvest_bob_tooling_stays_bobiverse_even_on_a_search_job():
    """Split rule: chair/worker/fleet lessons stay on bobiverse."""
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HARVEST_PS1),
        "-JobRepo",
        "SimonBarnett/a-search",
        "-Summary",
        "bob-worker done-miss release_gen",
        "-Lesson",
        "bob-worker BoredEmitter must set _release_gen on done-miss",
        "-DryRun",
    ]
    run = subprocess.run(args, capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    assert run.returncode == 0, run.stdout + run.stderr
    text = (run.stdout or "") + "\n" + (run.stderr or "")
    payload = json.loads(text[text.find("{") : text.rfind("}") + 1])
    assert payload["repo"] == "SimonBarnett/bobiverse"
    book = (payload.get("source") or {}).get("skill_book") or ""
    assert book in ("bobiverse-bob-worker", "harvest") or book.startswith("bobiverse-")


def test_fr3189_resolve_skill_book_a_search_never_bobiverse_harvest_path():
    book, path = intake.resolve_skill_book(
        repo="SimonBarnett/a-search",
        skill_book="harvest",
        title="lesson(harvest): a-search Parts",
        body="Lessons:\n- a-search provider query\n",
    )
    assert path != "common/.grok/skills/harvest/SKILL.md"
    assert path.replace("\\", "/").endswith("harvest-agent-skills/SKILL.md") or book == "harvest-agent-skills"
    assert "common/.grok/skills/harvest/" not in path.replace("\\", "/")


def test_fr3189_resolve_skill_book_bobiverse_unchanged():
    book, path = intake.resolve_skill_book(
        repo="SimonBarnett/bobiverse",
        skill_book="harvest",
        title="generic tip",
        body="Lessons:\n- something about intake\n",
    )
    assert book == "harvest"
    assert path == "common/.grok/skills/harvest/SKILL.md"


def test_fr3189_bob_worker_harvest_repo_helper():
    import sys

    sys.path.insert(0, str(ROOT / "bob" / "scripts"))
    import bob_worker as bw

    assert bw.harvest_repo_for_job("SimonBarnett/a-search#122") == "SimonBarnett/a-search"
    assert bw.harvest_repo_for_job("simonbarnett/a-search#9") == "SimonBarnett/a-search"
    assert bw.harvest_repo_for_job("SimonBarnett/bobiverse#3189") == "SimonBarnett/bobiverse"
    assert bw.harvest_repo_for_job(None) == "SimonBarnett/bobiverse"
    args_a = bw.harvest_invoke_repo_args("SimonBarnett/a-search#55")
    assert "-Repo" in args_a and "SimonBarnett/a-search" in args_a
    args_b = bw.harvest_invoke_repo_args("SimonBarnett/bobiverse#1")
    assert "SimonBarnett/bobiverse" in args_b


def test_fr3189_seat_env_exports_bob_job_repo(tmp_path: Path):
    import sys

    sys.path.insert(0, str(ROOT / "bob" / "scripts"))
    import bob_worker as bw

    env = bw.seat_env_extra(tmp_path / "run", "marchhare", "marchhare-1", job_repo="SimonBarnett/a-search")
    assert env.get("BOB_JOB_REPO") == "SimonBarnett/a-search"
    env2 = bw.seat_env_extra(tmp_path / "run2", "marchhare", "marchhare-2")
    assert "BOB_JOB_REPO" not in env2 or not env2.get("BOB_JOB_REPO")
