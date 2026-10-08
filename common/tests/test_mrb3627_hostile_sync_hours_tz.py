"""Hostile pins for MRB #3627 (Sync FR #3622) + FR #3629 bobhours ZoneInfo import."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

from repo_layout import ROOT


def test_mrb3627_sync_tip_ok_clean_agent_fetched_only():
    text = (ROOT / "common" / "scripts" / "Sync-BobiverseFromRepo.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "cleanAgentFetchedOnly" in text
    assert "fetched only, work tree untouched" in text
    assert "notmatch" in text and "dirty" in text


def test_mrb3627_worktree_appends_dirty_marker():
    text = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "; dirty" in text
    assert "$dirty" in text


def test_mrb3627_fleet_ops_skill_cites_fr3622():
    text = (
        ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "FR #3622" in text
    assert "clean agent" in text.lower() or "clean off-main" in text


def test_mrb3629_bobhours_london_tz_falls_back(monkeypatch):
    """london_tz must not raise when ZoneInfo('Europe/London') is unavailable."""
    from datetime import timezone
    from zoneinfo import ZoneInfoNotFoundError

    import bobhours as bh

    def boom(_key):
        raise ZoneInfoNotFoundError("Europe/London")

    monkeypatch.setattr(bh, "ZoneInfo", boom)
    monkeypatch.setitem(sys.modules, "tzdata", None)
    bh._LONDON = None
    tz = bh.london_tz()
    assert tz is timezone.utc


def test_mrb3629_bobcallback_imports_clean():
    import bobcallback  # noqa: F401

    assert hasattr(bobcallback, "HOURS_PATH")
    assert bobcallback.HOURS_PATH == "/bob/v1/hours"


def test_mrb3629_ci_installs_tzdata():
    yml = (ROOT / ".github" / "workflows" / "pytest-gitclaim.yml").read_text(
        encoding="utf-8"
    )
    assert "tzdata" in yml
