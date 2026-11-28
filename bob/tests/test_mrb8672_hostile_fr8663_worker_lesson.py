"""MRB #8672 hostile: pin bobiverse-bob-worker FR #8663 EXIT_PLAN_CHILD lesson."""
from __future__ import annotations

from pathlib import Path

WORKER_SKILL = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-worker"
    / "lessons.md"
)


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


def test_mrb8672_worker_skill_pins_fr8663_exit_plan_child():
    text = _utf8_no_bom(WORKER_SKILL)
    assert "**FR #8663:**" in text
    idx = text.index("**FR #8663:**")
    window = text[idx : idx + 520]
    assert "EXIT_PLAN_CHILD" in window
    assert "run_plan" in window
    assert "4294967295" in window
    assert "heal tip" in window
    assert "currently masks" not in window
    assert "Do not park this playbook under `harvest/SKILL.md`" in window
    assert "FR #7916" in window
