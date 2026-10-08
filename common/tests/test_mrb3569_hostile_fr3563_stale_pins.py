"""MRB #3569 hostile pins for FR #3563 common-suite stale-pin heal."""
from __future__ import annotations

from pathlib import Path

import repo_layout

ROOT = Path(repo_layout.ROOT)


def test_mrb3569_intake_py_is_pure_ascii_no_ellipsis():
    """FR #2926 / #3563: intake.py must stay ASCII (no U+2026 / em dash)."""
    raw = (ROOT / "common" / "scripts" / "intake.py").read_bytes()
    assert raw == raw.decode("ascii").encode("ascii")
    text = raw.decode("ascii")
    assert "\u2026" not in text
    assert "\u2014" not in text


def test_mrb3569_fr1565_sync_env_sets_sync_from_repo():
    """FR #3289 / #3563: all Sync subprocess env blocks opt into sync."""
    src = (ROOT / "common" / "tests" / "test_fr1565_sync_arp_version_truth.py").read_text(
        encoding="utf-8"
    )
    assert src.count('env["BOBIVERSE_SYNC_FROM_REPO"] = "1"') >= 3


def test_mrb3569_mrb2714_heading_pin_is_prefix():
    """Heading may append / FR #3299 / FR #3317; pin is prefix, not exact close."""
    src = (
        ROOT / "common" / "tests" / "test_mrb2714_hostile_harvest_lessons.py"
    ).read_text(encoding="utf-8")
    assert 'assert "## Harvest-lesson intake PRs (FR #2705)" in text' not in src
    assert "## Harvest-lesson intake PRs (FR #2705" in src