"""skills-visionary#61/#63: explicit -Repo skills-visionary must not keyword-split.

Plan how-to-plan lessons that mention tipform / bob-worker (FR #3004 / #3959 cues)
must stay on SimonBarnett/skills-visionary when -Repo is explicit (FR #3318).
FR #3959 a-search rewrite remains (see test_fr3959_no_bob_stub_on_product_harvest).
"""
from __future__ import annotations

import json
import os
import subprocess

from repo_layout import ROOT

HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"


def _dry_run(repo: str, summary: str, lesson: str, env: dict | None = None) -> tuple[dict, str]:
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
        summary,
        "-Lesson",
        lesson,
        "-DryRun",
    ]
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
        env=run_env,
    )
    text = (run.stdout or "") + "\n" + (run.stderr or "")
    assert run.returncode == 0, text[-2000:]
    start, end = text.find("{"), text.rfind("}")
    assert start >= 0 and end > start, text[-2000:]
    return json.loads(text[start : end + 1]), text


def test_sv61_tipform_cue_keeps_explicit_skills_visionary():
    """Class of #61 / bobiverse#6140: TipForm in how-to-plan must not rewrite repo."""
    payload, text = _dry_run(
        "SimonBarnett/skills-visionary",
        "When operator asserts ear publishes digest, verify live publisher (tray TipForm)",
        "how-to-plan: verify digest publisher before lock; OpenCode via merged PR; TipForm mocks",
    )
    assert payload["repo"] == "SimonBarnett/skills-visionary", text[-1500:]
    book = (payload.get("source") or {}).get("skill_book") or ""
    assert book == "harvest-skills-visionary", text[-1500:]
    path = (payload.get("source") or {}).get("skill_book_path") or payload.get(
        "skill_book_path"
    )
    assert path == ".grok/skills/harvest-skills-visionary/SKILL.md"
    assert "FR #3189/#3959 split" not in text
    assert "FR #3318" in text


def test_sv63_bob_worker_cue_keeps_explicit_skills_visionary():
    """Class of #63 / bobiverse#6155: bob-worker word in Plan lesson must not rewrite."""
    payload, text = _dry_run(
        "SimonBarnett/skills-visionary",
        "Plan seat how-to-plan: when bob-worker agent kind is on main probe live",
        "how-to-plan: OpenCode via merged PR; bob-worker probe stays on skills-visionary",
    )
    assert payload["repo"] == "SimonBarnett/skills-visionary", text[-1500:]
    book = (payload.get("source") or {}).get("skill_book") or ""
    assert book == "harvest-skills-visionary", text[-1500:]
    assert book != "bobiverse-bob-worker"
    assert "FR #3318" in text


def test_sv61_plan_seat_nick_keeps_skills_visionary_without_explicit_flag_shape():
    """seat=*-plan on skills-visionary JobRepo path also keeps the honesty box.

    Explicit -Repo is still the primary contract; this covers marchhare-plan style
    seats when Repo is already skills-visionary (ExplicitRepo true in this call,
    nick documents Plan-seat INFO path).
    """
    payload, text = _dry_run(
        "SimonBarnett/skills-visionary",
        "Plan TipForm mock pack",
        "how-to-plan: TipForm mocks belong with plan vision packs",
        env={"BOB_NICK": "marchhare-plan"},
    )
    assert payload["repo"] == "SimonBarnett/skills-visionary", text[-1500:]
    book = (payload.get("source") or {}).get("skill_book") or ""
    assert book == "harvest-skills-visionary"


def test_sv61_a_search_done_miss_still_rewrites_per_fr3959():
    """FR #3959 must keep rewriting a-search + bob-worker cues to bobiverse."""
    payload, text = _dry_run(
        "SimonBarnett/a-search",
        "FR a-search#3949 GIVEUP on done-miss: ACK only, no PR",
        "On bob-worker done-miss after ACK with no PR, GIVEUP FR immediately",
    )
    assert payload["repo"] == "SimonBarnett/bobiverse", text[-1500:]
    book = (payload.get("source") or {}).get("skill_book") or ""
    assert book == "bobiverse-bob-worker"
