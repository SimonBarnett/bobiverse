"""MRB #6594 hostile: FR #6567 fr2339 fixture under FR #4512 pin cues."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / "jeeves" / "tests" / "test_jeeves_hands_out_work.py"


def test_mrb6594_autouse_registers_marchhare_and_clears_exclude():
    src = PIN.read_text(encoding="utf-8")
    i = src.find("def _home(tmp_path, monkeypatch):")
    assert i >= 0
    window = src[i : i + 700]
    assert 'BOB_CHANSERV_EXCLUDE' in window
    assert '"marchhare"' in window
    assert not PIN.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb6594_mrb_pin_uses_needs_ionos_label_not_bare_stamp_alone():
    src = PIN.read_text(encoding="utf-8")
    i = src.find("def test_fr2339_sibling_ignores_pinned_out_other_machine")
    assert i >= 0
    window = src[i : i + 2800]
    assert 'labels=["needs-ionos"]' in window
    assert "FR #4512" in window
    assert "_seed_three_seat_digest" in window
    assert "pr_exists=None" in window
    assert 'row_blocked_for_machine(row, "marchhare-40208") is True' in window


def test_mrb6594_uat_param_covers_pinned_and_unpinned():
    src = PIN.read_text(encoding="utf-8")
    assert "def test_fr2339_uat_sibling_ignores_pinned_out_other_machine" in src
    assert '@pytest.mark.parametrize("pinned", [True, False])' in src
    i = src.find("def test_fr2339_uat_sibling_ignores_pinned_out_other_machine")
    window = src[i : i + 2200]
    assert "sibling_blocked is False" in window
    assert "sibling_blocked is True" in window
    assert 'status == "empty"' in window
