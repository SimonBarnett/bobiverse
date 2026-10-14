"""FR #4176: harvest must skip CLOSED wrong-book / process-loop closeouts (no FAIL-supersede token)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"


def _run_harvest(*extra: str) -> subprocess.CompletedProcess[str]:
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


def test_harvest_script_documents_fr4176_closed_wrong_book_skip():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #4176" in text
    assert "CLOSED" in text and "wrong" in text.lower()
    assert "Test-HarvestFailSupersedeProcessLoop" in text
    assert "SKIPPED harvest FAIL-supersede process loop" in text


def test_harvest_skips_closed_wrong_book_without_fail_supersede(tmp_path: Path):
    """Class of tip #4175: CLOSED wrong-book + under harvest/SKILL.md, no FAIL-supersede token."""
    r = _run_harvest(
        "-Summary",
        "MRB #4171 harvest tip CLOSED wrong-book: meta Re-offered FR / FR #2970 process already on main",
        "-Lesson",
        "Harvest tip that restates job-fr Re-offered FR wrong-book closeout under harvest/SKILL.md is itself FR #2970 wrong-book; CLOSE unmerged DONE PASS",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede process loop" in r.stdout
    assert "HARVESTED" not in r.stdout
    assert "QUEUED" not in r.stdout
    assert not list((tmp_path / "harvest-outbox").glob("*.json")) if (tmp_path / "harvest-outbox").exists() else True


def test_harvest_skips_done_pass_3317_process_loop(tmp_path: Path):
    r = _run_harvest(
        "-Summary",
        "MRB #4174 harvest tip CLOSED wrong-book process-loop; DONE PASS FR #3317",
        "-Lesson",
        "Harvest tip restating merged job-mrb product skill under harvest/SKILL.md is wrong-book; CLOSE unmerged DONE PASS FR #3317",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede process loop" in r.stdout
    assert "HARVESTED" not in r.stdout


def test_harvest_still_posts_real_product_playbook(tmp_path: Path):
    """Real product playbooks still attempt POST/queue — not skipped by FR #4176 needles."""
    r = _run_harvest(
        "-Summary",
        "FR #4176: harvest OutboxDir path must stay under LocalAppData on WinPS seats",
        "-Lesson",
        "Invoke-BobiverseHarvest -OutboxDir defaults to LocalAppData Bobiverse harvest-outbox.",
        "-OutboxDir",
        str(tmp_path / "harvest-outbox"),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SKIPPED harvest FAIL-supersede process loop" not in r.stdout
    assert "QUEUED" in r.stdout or "HARVESTED" in r.stdout
