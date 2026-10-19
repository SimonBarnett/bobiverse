"""FR #3959: never ADD bob/ bobiverse-bob-worker stubs into a-search.

When seats pass explicit -Repo SimonBarnett/a-search (FR #3189) and Summary/Lesson
cues trigger FR #3004 bobiverse-bob-worker inference, harvest must route the tip to
SimonBarnett/bobiverse (or refuse), not open a-search PRs that ADD
bob/.grok/skills/bobiverse-bob-worker/SKILL.md.
"""
from __future__ import annotations

import json
import subprocess

import intake
from repo_layout import ROOT

HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"


def _dry_run_repo_a_search_done_miss() -> tuple[dict, str]:
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HARVEST_PS1),
        "-Repo",
        "SimonBarnett/a-search",
        "-Summary",
        "FR a-search#3949 GIVEUP on done-miss: ACK only, no PR",
        "-Lesson",
        "On bob-worker done-miss after ACK with no PR, GIVEUP FR immediately",
        "-DryRun",
    ]
    run = subprocess.run(
        args, capture_output=True, text=True, timeout=60, cwd=str(ROOT)
    )
    assert run.returncode == 0, (run.stdout or "") + "\n" + (run.stderr or "")
    text = (run.stdout or "") + "\n" + (run.stderr or "")
    start, end = text.find("{"), text.rfind("}")
    assert start >= 0 and end > start, text[-2000:]
    return json.loads(text[start : end + 1]), text


def test_fr3959_explicit_repo_a_search_done_miss_routes_bobiverse():
    payload, text = _dry_run_repo_a_search_done_miss()
    assert payload["repo"] == "SimonBarnett/bobiverse", text[-1500:]
    book = (payload.get("source") or {}).get("skill_book") or ""
    assert book == "bobiverse-bob-worker"
    path = (payload.get("source") or {}).get("skill_book_path") or payload.get(
        "skill_book_path"
    )
    assert path == "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"
    assert "bob/.grok/skills/bobiverse-bob-worker" in text or path.endswith(
        "bobiverse-bob-worker/SKILL.md"
    )
    # Must not claim the tip lands on a-search.
    assert payload["repo"] != "SimonBarnett/a-search"


def test_fr3959_intake_rewrites_product_repo_when_book_is_bobiverse():
    """Defense in depth: intake must not create bob/ tips on a-search."""
    repo = intake.rewrite_harvest_repo_for_skill_book(
        "SimonBarnett/a-search", "bobiverse-bob-worker"
    )
    assert repo == "SimonBarnett/bobiverse"
    # Product honesty-box books stay on the product.
    assert (
        intake.rewrite_harvest_repo_for_skill_book(
            "SimonBarnett/a-search", "harvest-agent-skills"
        )
        == "SimonBarnett/a-search"
    )


def test_fr3959_resolve_explicit_bob_worker_on_a_search_keeps_bob_path():
    """Book/path stay bob-worker; repo rewrite (above) owns the tip home."""
    book, path = intake.resolve_skill_book(
        repo="SimonBarnett/a-search",
        skill_book="bobiverse-bob-worker",
        title="harvest: done-miss",
        body="Lessons:\n- bob-worker done-miss GIVEUP\n",
    )
    assert book == "bobiverse-bob-worker"
    assert path.replace("\\", "/") == "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"
