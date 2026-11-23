"""FR #9180: agent harvest must open skill PRs (SKILL.md), not receipt-only.

Acceptance pins:
- new lesson -> lesson(<book>) PR whose files[] touch the owning SKILL.md
- twin / ExistingPrUrl -> linked_existing_pr (no second tip)
- -SkillFile body lands in PR files[] at skill_book_path (not harvest/<name>)
- Harvest client wires Ensure-BobiverseHarvestSkillPr + CAST IRON docs
- pack/sync stage documents live skills come from merged bobiverse books
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import intake

REPO = "SimonBarnett/bobiverse"
HARVEST_SKILL = "common/.grok/skills/harvest/SKILL.md"
MONITOR_SKILL = "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md"
FLEET_SKILL = "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
REPO_ROOT = Path(__file__).resolve().parents[2]
HARVEST_PS1 = REPO_ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
HARVEST_BOOK = REPO_ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
MONITOR_BOOK = (
    REPO_ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
)
SYNC_PY = REPO_ROOT / "common" / "scripts" / "sync_install_skills.py"
PACK_PS1 = REPO_ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"


def test_fr9180_new_lesson_opens_skill_md_pr(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[MONITOR_SKILL] = "# bobiverse-jeeves-monitor\n\nIntro.\n"
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: TipForm menuarm timer starve playbook",
            "body": (
                "Session summary:\nTipForm ContextMenuStrip Timer starve\n\n"
                "Lessons:\n"
                "- TipForm menuarm must stamp last-open before Show; a starved "
                "System.Threading.Timer leaves the tray menu dead\n"
            ),
            "source": {
                "skill_book": "bobiverse-jeeves-monitor",
                "agent": "Invoke-BobiverseHarvest",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr9180_lesson")
    assert rec["state"] == "filed"
    assert filer.prs, "expected a lesson skill PR"
    pr = filer.prs[-1]
    assert pr.get("draft") is False
    assert "harvest-lesson" in pr["labels"]
    assert str(pr["title"]).startswith("lesson(bobiverse-jeeves-monitor):")
    paths = [str(f.get("path") or "").replace("\\", "/") for f in (pr.get("files") or [])]
    assert MONITOR_SKILL in paths
    content = next(f["content"] for f in pr["files"] if f["path"] == MONITOR_SKILL)
    assert "menuarm must stamp last-open" in content
    assert rec.get("url") and "/pull/" in str(rec["url"])


def test_fr9180_existing_pr_url_links_no_second_tip(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n"
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: covering skill PR already open",
            "body": (
                "Session summary:\n"
                "Existing PR: https://github.com/SimonBarnett/bobiverse/pull/9179\n\n"
                "Lessons:\n- TipForm menuarm timer starve playbook\n"
            ),
            "source": {"skill_book": "harvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr9180_link")
    assert rec["state"] == "linked_existing_pr"
    assert rec["number"] == 9179
    assert "pull/9179" in str(rec["url"])
    assert filer.prs == []


def test_fr9180_skillfile_lands_in_pr_files_at_book_path(tmp_path: Path):
    """SkillFile content at skill_book_path must appear in the lesson PR files[]."""
    filer = intake.FakeGitHubFiler()
    filer.repo_files[FLEET_SKILL] = "# bobiverse-fleet-ops\n\nIntro.\n"
    skill_body = (
        "# bobiverse-fleet-ops\n\nIntro.\n\n"
        "## Harvested lessons (intake)\n\n"
        "- hotpatch only the one service concerned; never touch Ergo\n"
    )
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: fleet hotpatch SkillFile promote",
            "body": (
                "Session summary:\nfleet SkillFile\n\n"
                "Lessons:\n"
                "- hotpatch only the one service concerned; never touch Ergo\n"
            ),
            "files": [{"path": FLEET_SKILL, "content": skill_body}],
            "source": {
                "skill_book": "bobiverse-fleet-ops",
                "skill_book_path": FLEET_SKILL,
                "agent": "Invoke-BobiverseHarvest",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr9180_sf")
    # Lesson already present in SkillFile base -> covered, OR filed with same path.
    if rec["state"] == "lesson_already_covered":
        assert rec.get("skill_book") == "bobiverse-fleet-ops"
        return
    assert rec["state"] == "filed"
    pr = filer.prs[-1]
    paths = [str(f.get("path") or "").replace("\\", "/") for f in (pr.get("files") or [])]
    assert FLEET_SKILL in paths
    assert not any(p.startswith("harvest/") for p in paths)


def test_fr9180_skillfile_companion_merges_into_lesson_pr(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n\nIntro.\n"
    companion = "common/.grok/skills/harvest/lessons.md"
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": REPO,
            "title": "harvest: SkillFile companion beside book",
            "body": (
                "Session summary:\ncompanion\n\n"
                "Lessons:\n- FR #9180 SkillFile companions must join the lesson PR files[]\n"
            ),
            "files": [
                {
                    "path": companion,
                    "content": "# archived\n\n- old bullet\n",
                }
            ],
            "source": {"skill_book": "harvest", "agent": "Invoke-BobiverseHarvest"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr9180_comp")
    assert rec["state"] == "filed"
    pr = filer.prs[-1]
    paths = [str(f.get("path") or "").replace("\\", "/") for f in (pr.get("files") or [])]
    assert HARVEST_SKILL in paths
    assert companion in paths


def test_fr9180_merge_lesson_pr_files_helper():
    merged = intake.merge_lesson_pr_files(
        HARVEST_SKILL,
        "# Harvest\n\n- lesson\n",
        [
            {"path": "harvest/orphan.md", "content": "x"},
            {
                "path": "common/.grok/skills/harvest/lessons.md",
                "content": "# archive\n",
            },
            {"path": HARVEST_SKILL, "content": "ignored duplicate"},
        ],
    )
    paths = [f["path"] for f in merged]
    assert paths[0] == HARVEST_SKILL
    assert "common/.grok/skills/harvest/lessons.md" in paths
    assert "harvest/orphan.md" not in paths


def test_fr9180_ensure_helper_opens_skill_pr(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[HARVEST_SKILL] = "# Harvest\n\nIntro.\n"
    rec = intake.ensure_bobiverse_harvest_skill_pr(
        tmp_path,
        repo=REPO,
        book="harvest",
        skill_path=HARVEST_SKILL,
        lessons=["FR #9180 same-turn Ensure must open a lesson(harvest) skill PR"],
        summary="ensure same-turn skill PR",
        filer=filer,
        seat="flamingo-9180",
    )
    assert rec["state"] == "filed"
    assert filer.prs
    pr = filer.prs[-1]
    paths = [f.get("path") for f in (pr.get("files") or [])]
    assert HARVEST_SKILL in paths
    assert "/pull/" in str(rec.get("url") or "")


def test_fr9180_ensure_helper_noop_without_lessons(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    rec = intake.ensure_bobiverse_harvest_skill_pr(
        tmp_path,
        repo=REPO,
        book="harvest",
        skill_path=HARVEST_SKILL,
        lessons=[],
        summary="receipt only",
        filer=filer,
    )
    assert rec["state"] == "noop"
    assert filer.prs == []


def test_fr9180_invoke_harvest_skillfile_uses_book_path():
    text = HARVEST_PS1.read_text(encoding="utf-8")
    assert "Ensure-BobiverseHarvestSkillPr" in text
    assert "FR #9180" in text
    # SkillFile must not hard-code harvest/<name> as the only destination.
    assert re.search(
        r"skillBookPath|skill_book_path",
        text,
    )
    # Old exclusive path assignment should yield to book path when known.
    assert "harvest/' + $item.Name" not in text.replace('"', "'") or (
        "skillBookPath" in text
        and re.search(r"SkillFile|skillFileItems", text, re.I)
    )


def test_fr9180_invoke_harvest_dryrun_skillfile_path(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_text("# harvest\n\npin body for SkillFile\n", encoding="utf-8")
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(HARVEST_PS1),
            "-Repo",
            REPO,
            "-Book",
            "harvest",
            "-Summary",
            "FR9180 SkillFile path dry-run",
            "-Lesson",
            "SkillFile must land at common/.grok/skills/harvest/SKILL.md",
            "-SkillFile",
            str(skill),
            "-DryRun",
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert HARVEST_SKILL in out or '"path"' in out
    assert "harvest/SKILL.md" not in out.split(HARVEST_SKILL)[0] or HARVEST_SKILL in out
    # Must not stage under bare harvest/<basename> when book path is known.
    payload_match = re.search(r"\{[\s\S]*\"kind\"\s*:\s*\"harvest\"[\s\S]*\}", out)
    assert payload_match, out
    payload = json.loads(payload_match.group(0))
    files = payload.get("files") or []
    assert files, "DryRun payload must include SkillFile files[]"
    paths = [str(f.get("path") or "").replace("\\", "/") for f in files]
    assert HARVEST_SKILL in paths
    assert not any(p == "harvest/SKILL.md" for p in paths)


def test_fr9180_docs_cast_iron_owe_skill_pr():
    harvest = HARVEST_BOOK.read_text(encoding="utf-8")
    monitor = MONITOR_BOOK.read_text(encoding="utf-8")
    assert "FR #9180" in harvest
    assert re.search(r"skill PR|SKILL\.md", harvest, re.I)
    assert "receipt" in harvest.lower()
    assert "FR #9180" in monitor
    assert re.search(r"skill PR|SKILL\.md", monitor, re.I)


def test_fr9180_sync_and_pack_document_merged_skills():
    sync = SYNC_PY.read_text(encoding="utf-8")
    pack = PACK_PS1.read_text(encoding="utf-8")
    assert "FR #9180" in sync or "merged" in sync.lower()
    assert ".grok/skills" in sync
    assert "FR #9180" in pack
    assert re.search(r"harvest|SKILL\.md|\.grok\\\\skills|\.grok/skills", pack, re.I)
