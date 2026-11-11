"""docs/mrb-6680: hostile pins for FR #6661 / PR #6680.

Pins:
- ``_inject_line`` source windows must be method-bounded (fixed 2200/4000 miss markers)
- Tray Agents OpenCode free/paid defaults + ``[default]`` on free
- Copilot meter tests accept optional FR #6371 `` - updated HH:mm``
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BW = ROOT / "bob" / "scripts" / "bob_worker.py"
TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
T828 = ROOT / "bob" / "tests" / "test_tray_dialogs_828.py"


def _inject_method_body() -> str:
    src = BW.read_text(encoding="utf-8")
    i = src.index("def _inject_line")
    j = src.find("\n    def ", i + 1)
    assert j > i, "next class-level def after _inject_line missing"
    return src, i, j, src[i:j]


def test_mrb6680_inject_line_method_bound_covers_markers_fixed_windows_miss():
    src, i, j, body = _inject_method_body()
    assert "assign_job_ref" in body
    assert "ack_job_ref" in body
    assert "since_wall = time.time()" in body
    # Regression: OpenCode checklist growth pushed markers past fixed windows.
    assert "assign_job_ref" not in src[i : i + 2200]
    assert "since_wall = time.time()" not in src[i : i + 4000]
    # Slice must stop at the next class-level def, not a nested body def.
    assert body.rstrip().endswith(":") or "def _inject_line" in body.splitlines()[0]
    assert "\n    def _wait_exit" in src[j : j + 40] or src[j:].lstrip().startswith("def ")


def test_mrb6680_product_pins_use_method_bound_slice():
    for rel in (
        "bob/tests/test_fr2791_submit_verify_stop_matches_job.py",
        "bob/tests/test_fr4889_grok_submit_verify_receipt_ack.py",
        "bob/tests/test_mrb2700_hostile_submit_verify.py",
    ):
        t = (ROOT / rel).read_text(encoding="utf-8")
        # Contiguous method-bound pattern near _inject_line pin (no fixed 2200/4000 window).
        assert 'find("\\n    def "' in t or "find('\\n    def '" in t, rel
        assert "i + 2200" not in t, rel
        assert "i + 4000" not in t, rel


def test_mrb6680_tray_opencode_free_paid_menu_defaults():
    tray = TRAY.read_text(encoding="utf-8")
    assert 'DefaultOpencodeFreeModel = "opencode/deepseek-v4.1-flash-free"' in tray
    assert 'DefaultOpencodePaidModel = "opencode-go/deepseek-v4-pro"' in tray
    assert 'freeText += " [default]"' in tray
    assert "Start free model (" in tray
    assert "Start paid model (" in tray
    # FR #6429: per-child env only; never SetEnvironmentVariable on tray process.
    assert "Environment.SetEnvironmentVariable" not in tray[tray.index("OnAgentChoiceClick") : tray.index("BeginRefreshAgentChoices")]


def test_mrb6680_copilot_line_accepts_updated_suffix():
    t = T828.read_text(encoding="utf-8")
    assert "def _copilot_line_matches" in t
    assert "updated" in t
    assert "fetched_at" in t
    # Helper must allow exact match OR optional ' - updated HH:mm'.
    assert r"( - updated \d{2}:\d{2})?" in t or "updated \\d{2}:\\d{2}" in t
    assert "Start free model (opencode/deepseek-v4.1-flash-free) [default]" in t
    assert "Start paid model (opencode-go/deepseek-v4-pro)" in t
