"""MRB #2723 hostile: bob-worker harvest digest lessons (FR #2705 audit)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WK = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
AUDIT = ROOT / "common" / "docs" / "harvest-lessons-audit-2026-10-06.md"


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


def test_mrb2723_digest_section_present():
    text = _utf8_no_bom(WK)
    assert "## Harvest digest (lessons audit 2026-10-06)" in text
    assert "FR #2705" in text or "audit for FR #2705" in text


def test_mrb2723_seat_inject_and_submit():
    text = _utf8_no_bom(WK)
    assert "Seat inject and submit" in text
    idx = text.index("Seat inject and submit")
    # FR #4469: re-paste / retry Enter sit just past 800 once the FR #4115 clause grew.
    window = text[idx : idx + 1000]
    assert "WriteConsoleInput" in window or "submit gap" in window
    assert "clipboard" in window.lower()
    assert "harvest_hold_s" in window or "!bored" in window
    assert "re-paste" in window or "retry Enter" in window


def test_mrb2723_tray_and_launch_parity():
    text = _utf8_no_bom(WK)
    assert "Tray and launch parity" in text
    idx = text.index("Tray and launch parity")
    window = text[idx : idx + 900]
    assert "describe-launch" in window or "describe_worker_exe_launch" in window
    assert "prepare_seat_child_env" in window or "CURSOR_*" in window
    assert "recycle_to_cap" in window or "seat roots" in window
    assert "tray.alive" in window or "WinForms" in window


def test_mrb2723_fleet_identity():
    text = _utf8_no_bom(WK)
    assert "Fleet identity" in text
    idx = text.index("Fleet identity")
    window = text[idx : idx + 500]
    assert "ionos" in window
    assert "canonical_worker_nick" in window or "machine-pid" in window


def test_mrb2723_audit_table_path_present():
    text = _utf8_no_bom(WK)
    assert "harvest-lessons-audit-2026-10-06.md" in text
    assert AUDIT.is_file(), AUDIT


def test_mrb2723_digest_bullets_complete_lines():
    """Digest completeness applies only to ## Harvest digest, not ## Harvested lessons.

    FR #6223: scanning to EOF pulled in `- **FR #N:**` intake bullets that are not
    digest audit lines (they need not end with `)` / lessons:/held).
    """
    text = _utf8_no_bom(WK)
    start = text.index("## Harvest digest (lessons audit 2026-10-06)")
    rest = text[start + 3 :]  # skip the digest heading's own ##
    nxt = rest.find("\n## ")
    chunk = text[start : start + 3 + nxt] if nxt >= 0 else text[start:]
    assert "## Harvested lessons" not in chunk
    bullets = [ln for ln in chunk.splitlines() if ln.startswith("- **")]
    assert len(bullets) >= 3
    for ln in bullets:
        assert ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln
        assert "orphan" not in ln.lower()


def test_mrb2723_harvested_lessons_fr_bullets_outside_digest_scan():
    """FR #6223: Harvested lessons may use `- **FR #` without digest closing paren."""
    text = _utf8_no_bom(WK)
    assert "## Harvested lessons (intake)" in text
    h_start = text.index("## Harvested lessons (intake)")
    # MRB #6224 / CodeRabbit: stop at next ## so a later section cannot satisfy the pin.
    h_rest = text[h_start + 3 :]
    h_nxt = h_rest.find("\n## ")
    h_chunk = text[h_start : h_start + 3 + h_nxt] if h_nxt >= 0 else text[h_start:]
    fr_bullets = [ln for ln in h_chunk.splitlines() if ln.startswith("- **FR #")]
    assert len(fr_bullets) >= 1
    # At least one FR intake bullet would fail the digest closing-paren rule.
    assert any(
        not (ln.rstrip().endswith(")") or "lessons:" in ln or "held" in ln)
        for ln in fr_bullets
    )
