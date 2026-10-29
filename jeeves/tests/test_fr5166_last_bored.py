"""FR #5166: persist last !bored time and feed stall detector 6."""
from __future__ import annotations

from pathlib import Path

import gitclaim
import stall_detectors as sd


def test_record_and_load_last_bored(tmp_path: Path):
    assert gitclaim.load_last_bored(tmp_path) == {}
    nick = gitclaim.record_last_bored(tmp_path, "flamingo-67876", now=1000.0)
    assert nick
    loaded = gitclaim.load_last_bored(tmp_path)
    assert loaded[nick] == 1000.0
    assert loaded[nick.lower()] == 1000.0
    gitclaim.record_last_bored(tmp_path, nick, now=2000.0)
    assert gitclaim.load_last_bored(tmp_path)[nick] == 2000.0


def test_merge_last_bored_picks_newer(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    gitclaim.record_last_bored(a, "ionos-1", now=10.0)
    gitclaim.record_last_bored(b, "ionos-1", now=30.0)
    gitclaim.record_last_bored(a, "marchhare-1", now=5.0)
    merged = gitclaim.merge_last_bored(a, b)
    ion = gitclaim.canonical_worker_nick("ionos-1") or "ionos-1"
    mh = gitclaim.canonical_worker_nick("marchhare-1") or "marchhare-1"
    assert merged[ion] == 30.0
    assert merged[mh] == 5.0


def test_stall_scan_uses_persisted_last_bored(tmp_path: Path):
    now = 50_000.0
    gitclaim.record_last_bored(tmp_path, "flamingo-1", now=now - sd.BORED_LATENCY_S - 5)
    snap = {
        "now": now,
        "idle": {"flamingo-1"},
        "last_bored": gitclaim.load_last_bored(tmp_path),
    }
    found = sd.detect_bored_latency(snap)
    assert found and found[0]["id"] == sd.BORED_LATENCY_ID


def test_irc_agent_bored_stamps_last_bored():
    src = (Path(__file__).resolve().parents[2] / "common" / "scripts" / "irc_agent.py").read_text(
        encoding="utf-8"
    )
    assert "record_last_bored" in src
    ch = (Path(__file__).resolve().parents[2] / "common" / "scripts" / "chair_health.py").read_text(
        encoding="utf-8"
    )
    assert "merge_last_bored" in ch
