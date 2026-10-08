# -*- coding: utf-8 -*-
"""MRB #3253 hostile gates for FR #3189 harvest JobRepo routing.

Pins after product PR #3253:
- a-search product DryRun → SimonBarnett/a-search + harvest-agent-skills
- bob tooling cues on an a-search JobRepo → bobiverse (PS1 split)
- resolve_skill_book(repo=a-search) never returns bobiverse common/harvest path
- write_job_repo_marker + seat_env BOB_JOB_REPO
- harvest skill documents FR #3189 routing
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import intake
from repo_layout import ROOT

HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
SKILL = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"


def _dry(job_repo: str, summary: str, lesson: str) -> dict:
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HARVEST_PS1),
        "-JobRepo",
        job_repo,
        "-Summary",
        summary,
        "-Lesson",
        lesson,
        "-DryRun",
    ]
    run = subprocess.run(args, capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    assert run.returncode == 0, (run.stdout or "") + (run.stderr or "")
    text = (run.stdout or "") + "\n" + (run.stderr or "")
    return json.loads(text[text.find("{") : text.rfind("}") + 1])


def test_mrb3253_product_job_routes_a_search():
    p = _dry(
        "SimonBarnett/a-search",
        "a-search awin Parts SELECT",
        "a-search awin local uses injectable mssql connect",
    )
    assert p["repo"] == "SimonBarnett/a-search"
    assert (p.get("source") or {}).get("skill_book") == "harvest-agent-skills"


def test_mrb3253_tooling_split_forces_bobiverse():
    p = _dry(
        "SimonBarnett/a-search",
        "bob-worker done-miss on a-search FR",
        "bob-worker BoredEmitter must set _release_gen on done-miss",
    )
    assert p["repo"] == "SimonBarnett/bobiverse"


def test_mrb3253_resolve_never_bobiverse_harvest_path_for_a_search():
    book, path = intake.resolve_skill_book(
        repo="SimonBarnett/a-search",
        skill_book="harvest",
        title="lesson: a-search entry JWT",
        body="Lessons:\n- a-search entry fan-out\n",
    )
    assert path != "common/.grok/skills/harvest/SKILL.md"
    assert "common/.grok/skills/harvest/" not in path.replace("\\", "/")
    assert book == "harvest-agent-skills"
    assert path.replace("\\", "/").endswith(".grok/skills/harvest-agent-skills/SKILL.md")


def test_mrb3253_write_job_repo_marker_and_env(tmp_path: Path):
    sys.path.insert(0, str(ROOT / "bob" / "scripts"))
    import bob_worker as bw

    run = tmp_path / "run"
    run.mkdir()
    repo = bw.write_job_repo_marker(run, "SimonBarnett/a-search#3189")
    assert repo == "SimonBarnett/a-search"
    assert (run / "job-repo.txt").read_text(encoding="utf-8").strip() == "SimonBarnett/a-search"
    env = bw.seat_env_extra(run, "marchhare", "marchhare-1", job_repo="SimonBarnett/a-search#9")
    assert env.get("BOB_JOB_REPO") == "SimonBarnett/a-search"


def test_mrb3253_job_repo_txt_beside_outbox(tmp_path: Path, monkeypatch):
    run = tmp_path / "worker-run"
    run.mkdir()
    outbox = run / "outbox.txt"
    outbox.write_text("", encoding="utf-8")
    (run / "job-repo.txt").write_text("SimonBarnett/a-search\n", encoding="utf-8")
    monkeypatch.setenv("BOB_OUTBOX", str(outbox))
    monkeypatch.delenv("BOB_JOB_REPO", raising=False)
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HARVEST_PS1),
        "-Summary",
        "a-search ebay Browse API",
        "-Lesson",
        "a-search ebay live Browse search",
        "-DryRun",
    ]
    env = os.environ.copy()
    env["BOB_OUTBOX"] = str(outbox)
    env.pop("BOB_JOB_REPO", None)
    runp = subprocess.run(args, capture_output=True, text=True, timeout=60, cwd=str(ROOT), env=env)
    assert runp.returncode == 0, runp.stdout + runp.stderr
    text = (runp.stdout or "") + "\n" + (runp.stderr or "")
    payload = json.loads(text[text.find("{") : text.rfind("}") + 1])
    assert payload["repo"] == "SimonBarnett/a-search"


def test_mrb3253_harvest_skill_documents_routing():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #3189" in text
    assert "JobRepo" in text or "BOB_JOB_REPO" in text
    assert "a-search" in text.lower()
    assert "harvest-agent-skills" in text
