"""FR #8493: auto-feed off must not stay silent when idle seats have offerable rows."""
from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

from repo_layout import ROOT

MON = ROOT / "jeeves" / "tools" / "monitor"
if str(MON) not in sys.path:
    sys.path.insert(0, str(MON))

import auto_feed  # noqa: E402
import idle_seats  # noqa: E402
from _common import EXIT_FINDING, EXIT_OK  # noqa: E402


def _args(tmp_path: Path) -> Namespace:
    chair = tmp_path / "chair"
    chair.mkdir()
    return Namespace(chair_home=str(chair), digest_home=str(tmp_path / "digest"))


def test_unconfigured_stays_ok_when_no_idle_offerable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        idle_seats,
        "check",
        lambda args: ({"idle_seats": [], "offerable_for_live_seats": 0, "findings": []}, EXIT_OK),
    )
    doc, code = auto_feed.check(_args(tmp_path))
    assert code == EXIT_OK
    assert doc["configured"] is False
    assert doc["enabled"] is False
    assert doc["findings"] == []


def test_unconfigured_finding_when_idle_and_offerable(tmp_path, monkeypatch):
    monkeypatch.setattr(
        idle_seats,
        "check",
        lambda args: (
            {
                "idle_seats": [{"nick": "flamingo-1"}],
                "offerable_for_live_seats": 2,
                "findings": ["1 idle seat(s) with 2 offerable row(s)"],
            },
            EXIT_FINDING,
        ),
    )
    doc, code = auto_feed.check(_args(tmp_path))
    assert code == EXIT_FINDING
    assert doc["ok"] is False
    assert doc["configured"] is False
    assert doc["enabled"] is False
    text = " ".join(doc["findings"])
    assert "auto-feed off" in text
    assert "1 idle" in text
    assert "2 offerable" in text
    assert "!bored" in text


def test_enabled_auto_feed_does_not_alert_on_idle(tmp_path, monkeypatch):
    chair = tmp_path / "chair"
    chair.mkdir()
    (chair / "auto-feed.json").write_text('{"enabled": true}\n', encoding="utf-8")
    monkeypatch.setattr(
        idle_seats,
        "check",
        lambda args: (
            {
                "idle_seats": [{"nick": "flamingo-1"}],
                "offerable_for_live_seats": 4,
                "findings": ["idle"],
            },
            EXIT_FINDING,
        ),
    )
    doc, code = auto_feed.check(Namespace(chair_home=str(chair), digest_home=str(tmp_path / "digest")))
    assert code == EXIT_OK
    assert doc["enabled"] is True
    assert doc["findings"] == []
