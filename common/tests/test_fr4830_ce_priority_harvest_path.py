"""FR #4830: ce-priority must not invent common/.grok/skills/harvest tip path."""
from __future__ import annotations

from pathlib import Path

import intake

CE_REPO = "SimonBarnett/ce-priority"
DW_LAUNCHER = "dayworks/.grok/skills/dayworks-launcher/SKILL.md"
INVENT_HARVEST = "common/.grok/skills/harvest/SKILL.md"


def test_fr4830_product_default_maps_ce_priority_to_dayworks_launcher():
    entry = intake.PRODUCT_DEFAULT_SKILL_BOOK.get(CE_REPO.lower())
    assert entry is not None
    book, path = entry
    assert book == "dayworks-launcher"
    assert path.replace("\\", "/") == DW_LAUNCHER
    assert INVENT_HARVEST not in path.replace("\\", "/")


def test_fr4830_resolve_skill_book_never_invents_common_harvest():
    book, path = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: tip-loop close",
        body="Lessons:\n- never invent common harvest on ce-priority\n",
        repo=CE_REPO,
    )
    assert book == "dayworks-launcher"
    assert path.replace("\\", "/") == DW_LAUNCHER

    book2, path2 = intake.resolve_skill_book(
        skill_book="",
        title="harvest: misc",
        body="Lessons:\n- generic park\n",
        repo=CE_REPO,
    )
    assert book2 == "dayworks-launcher"
    assert path2.replace("\\", "/") == DW_LAUNCHER


def test_fr4830_file_submission_opens_dayworks_launcher_not_invent(
    tmp_path: Path,
):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[DW_LAUNCHER] = (
        "# dayworks-launcher\n\n## Harvested lessons (intake)\n\n"
    )
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": CE_REPO,
            "title": "harvest: assert-lock tip-loop",
            "body": (
                "Session summary:\nCLOSED wrong-path invent-harvest\n\n"
                "Lessons:\n- park under dayworks-launcher; never invent common harvest\n"
            ),
            "source": {
                "skill_book": "harvest",
                "agent": "Invoke-BobiverseHarvest",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr4830")
    # May skip as lesson_review / already covered; if filed, must not invent path.
    if rec.get("state") == "filed" and filer.prs:
        pr = filer.prs[-1]
        paths = [str(f.get("path") or "").replace("\\", "/") for f in pr.get("files") or []]
        assert DW_LAUNCHER in paths
        assert INVENT_HARVEST not in paths
        assert str(pr.get("title") or "").startswith("lesson(dayworks-launcher):")
    else:
        # Skip paths still must resolve book away from invent harvest.
        book, path = intake.resolve_skill_book(
            skill_book="harvest",
            title=norm["title"],
            body=norm["body"],
            repo=CE_REPO,
        )
        assert book == "dayworks-launcher"
        assert path.replace("\\", "/") == DW_LAUNCHER


def test_fr4830_invoke_harvest_ps1_routes_ce_priority():
    # common/tests -> common/scripts/Invoke-BobiverseHarvest.ps1
    ps1 = Path(__file__).resolve().parents[1] / "scripts" / "Invoke-BobiverseHarvest.ps1"
    text = ps1.read_text(encoding="utf-8")
    assert "SimonBarnett/ce-priority" in text
    assert "dayworks-launcher" in text
    assert "FR #4830" in text or "4830" in text
    assert "dayworks/.grok/skills/dayworks-launcher/SKILL.md" in text
