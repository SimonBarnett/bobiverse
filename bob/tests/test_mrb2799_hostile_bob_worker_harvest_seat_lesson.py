"""MRB #2799 hostile: bobiverse-bob-worker harvest lesson pins BOB_NICK seat stamp."""
from __future__ import annotations

from pathlib import Path

WORKER_DIR = (
    Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-worker"
)
WORKER_SKILL = WORKER_DIR / "SKILL.md"
WORKER_LESSONS = WORKER_DIR / "lessons.md"
def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2799_worker_skill_has_harvested_seat_nick_lesson():
    text = _utf8_no_bom(WORKER_LESSONS)
    assert "## Harvested lessons (intake)" in text
    idx = text.index("## Harvested lessons (intake)")
    section = text[idx:]
    assert "BOB_NICK" in section
    assert "BOB_AGENT_NICK" in section
    assert "seat_env_extra" in section
    assert "2790" in section or "2795" in section
    # Contiguous playbook: prefer BOB_NICK then agent nick for seat= / self-MRB
    bullet_idx = section.index("BOB_NICK")
    window = section[bullet_idx : bullet_idx + 280]
    assert "BOB_AGENT_NICK" in window
    assert "seat" in window.lower()
    assert "self-MRB" in window or "self-MRB" in section


def test_mrb2799_lesson_names_invoke_harvest_and_export_both():
    text = _utf8_no_bom(WORKER_LESSONS)
    idx = text.index("## Harvested lessons (intake)")
    section = text[idx:]
    assert "Invoke-BobiverseHarvest" in section
    assert "prefer BOB_NICK" in section or "BOB_NICK then BOB_AGENT_NICK" in section
    assert "export both" in section or "seat_env_extra must export both" in section


def test_mrb2799_hygiene_no_orphan_after_digest():
    """Digest stays complete in the operating manual. Intake bullets are lessons.md."""
    text = _utf8_no_bom(WORKER_SKILL)
    digest = text.index("## Harvest digest")
    assert "## Harvested lessons (intake)" not in text
    assert "lessons.md" in text[digest:]
    between = text[digest:]
    assert "**Fleet identity:**" in between
    assert "held intake row)" in between
    lessons = _utf8_no_bom(WORKER_LESSONS)
    assert "## Harvested lessons (intake)" in lessons
