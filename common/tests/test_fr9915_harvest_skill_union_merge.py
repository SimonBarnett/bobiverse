# -*- coding: utf-8 -*-
"""FR #9915: harvest-lesson tips must not CONFLICT on the same SKILL.md append hunk."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "common" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import intake as intake_mod  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed rc={r.returncode}\n{r.stdout}\n{r.stderr}"
        )
    return (r.stdout or "").strip()


def test_fr9915_gitattributes_union_for_harvest_skill_books():
    ga = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "common/.grok/skills/harvest/SKILL.md" in ga
    assert "merge=union" in ga
    assert "common/.grok/skills/harvest/lessons.md" in ga


def test_fr9915_two_tip_appends_merge_clean_with_union(tmp_path: Path):
    """Simulate two harvest tips appending different bullets; union keeps both."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "fr9915@example.com")
    _git(repo, "config", "user.name", "fr9915")
    skill = repo / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    base = (
        "# harvest\n\n"
        + intake_mod.HARVESTED_LESSONS_HEADING
        + "\n\n"
        + "- base lesson already on main\n"
    )
    skill.write_text(base, encoding="utf-8", newline="\n")
    ga = repo / ".gitattributes"
    ga.write_text(
        "common/.grok/skills/harvest/SKILL.md merge=union\n",
        encoding="utf-8",
        newline="\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    _git(repo, "branch", "-M", "main")

    _git(repo, "checkout", "-b", "tip-a")
    skill.write_text(
        intake_mod.apply_lessons_to_skill_md(base, ["lesson A from tip-a"]),
        encoding="utf-8",
        newline="\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "tip-a")

    _git(repo, "checkout", "main")
    _git(repo, "checkout", "-b", "tip-b")
    skill.write_text(
        intake_mod.apply_lessons_to_skill_md(base, ["lesson B from tip-b"]),
        encoding="utf-8",
        newline="\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "tip-b")

    # Merge tip-a into tip-b (same collision class as bulk MRB).
    r = subprocess.run(
        ["git", "merge", "--no-edit", "tip-a"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    text = skill.read_text(encoding="utf-8")
    assert r.returncode == 0, f"merge failed:\n{r.stdout}\n{r.stderr}\n{text}"
    assert "<<<<<<<" not in text
    assert "lesson A from tip-a" in text
    assert "lesson B from tip-b" in text
    assert "base lesson already on main" in text


def test_fr9915_apply_lessons_still_appends_under_heading():
    base = "# x\n\n" + intake_mod.HARVESTED_LESSONS_HEADING + "\n\n- old\n"
    out = intake_mod.apply_lessons_to_skill_md(base, ["brand new lesson"])
    assert "brand new lesson" in out
    assert out.count(intake_mod.HARVESTED_LESSONS_HEADING) == 1