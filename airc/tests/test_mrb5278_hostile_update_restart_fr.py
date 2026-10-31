"""Hostile pin for MRB #5278 airc remote UPDATE restart FR vision (docs-only)."""
from __future__ import annotations

from repo_layout import ROOT

FR = ROOT / "airc/docs/feature-request-airc-remote-update-restart-2026-10-31.md"


def test_mrb5278_fr_vision_exists_utf8_no_bom():
    assert FR.is_file()
    raw = FR.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    assert "\ufffd" not in text


def test_mrb5278_extends_fr77_and_locks_s2_restart():
    text = FR.read_text(encoding="utf-8")
    for h in (
        "## Objective",
        "## Success",
        "## LOCKED",
        "## UNKNOWN",
        "## Implementation slices",
    ):
        assert h in text, f"missing {h}"
    assert "FR #77" in text
    assert "second update channel" in text
    assert "| S2 |" in text
    assert "Restart under all conditions" in text
    assert "Ensure-ServiceRunning" in text
    assert "120s" in text
    assert "msiexec-timeout" in text
    assert "VERSION" in text
    assert "intake" in text.lower()
    locked = text[text.index("## LOCKED") : text.index("## UNKNOWN")]
    assert "S2" in locked
    assert "FR #77" in locked


def test_mrb5278_anti_omnibus_points_at_fr_a_first():
    text = FR.read_text(encoding="utf-8")
    assert "FR-A" in text
    assert "many small" in text.lower() or "Anti-omnibus" in text or "anti-omnibus" in text.lower()