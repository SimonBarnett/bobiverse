"""FR #5569: harvest open-twin must not link a product FR PR."""
from __future__ import annotations

from pathlib import Path

import intake

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
LESSON = (
    "EXTENSION status must not write HKLM; ForceInstall fill-holes appends "
    "a free value name and never targets domain controllers."
)


class _AllOpenPullsFiler(intake.FakeGitHubFiler):
    """Live GhCliFiler.list_open_pulls returns every open PR, including product FRs."""

    def list_open_pulls(self, repo: str) -> list[dict]:
        return [r for r in self.prs if str(r.get("repo") or "") == repo and not r.get("closed")]


def test_fr5569_product_pr_is_not_open_lesson_twin():
    filer = _AllOpenPullsFiler()
    filer.prs.append(
        {
            "repo": REPO,
            "number": 5568,
            "title": "FR #5538: EXTENSION status read-only; append forcelist; skip DCs",
            "body": (
                "Keep EXTENSION status read-only and append forcelist slots.\n"
                "Fill-holes skips DCs, never overwrites value name 1.\n"
                "Closes SimonBarnett/bobiverse#5538\n"
            ),
            "labels": [],
            "url": f"https://github.com/{REPO}/pull/5568",
            "branch": "fr-5538",
            "draft": False,
        }
    )
    hit = intake.find_open_harvest_lesson_twin(filer, REPO, [LESSON], seat="flamingo-53764")
    assert hit is None


def test_fr5569_file_submission_opens_lesson_not_product_url(tmp_path: Path):
    filer = _AllOpenPullsFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n\n## Harvested lessons (intake)\n"
    filer.prs.append(
        {
            "repo": REPO,
            "number": 5568,
            "title": "FR #5538: EXTENSION status read-only; append forcelist; skip DCs",
            "body": "EXTENSION status fill-holes ForceInstall domain controllers.\n",
            "labels": [],
            "url": f"https://github.com/{REPO}/pull/5568",
            "branch": "fr-5538",
        }
    )
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: FR 5538 EXTENSION status is read-only",
            "body": f"Session summary:\nFR 5538\n\nLessons:\n- {LESSON}\n",
            "idempotency_key": "hv-fr5569-a",
            "source": {
                "skill_book": "harvest",
                "agent": "Invoke-BobiverseHarvest",
                "machine": "flamingo",
                "seat": "flamingo-53764",
            },
        }
    )
    assert err is None, err
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr5569a")
    assert rec["state"] == "filed"
    assert rec["url"] != f"https://github.com/{REPO}/pull/5568"
    assert rec.get("number") != 5568
    assert any(
        str(p.get("title") or "").startswith("lesson(") for p in filer.prs
    )
