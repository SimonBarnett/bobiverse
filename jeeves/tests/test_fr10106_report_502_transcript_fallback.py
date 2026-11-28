"""FR #10106: monitor probe + inbound-transcript fallback when /report returns 502."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))
sys.path.insert(0, str(ROOT / "jeeves" / "tools" / "monitor"))

import inbound_transcript as it  # noqa: E402
import _common as monitor_common  # noqa: E402
import disk_starvation as ds  # noqa: E402


def test_probe_live_report_http_502(monkeypatch):
    import urllib.error
    import urllib.request

    def _open(*_a, **_k):
        raise urllib.error.HTTPError(
            "https://bob.ntsa.uk/bob/v1/report", 502, "Bad Gateway", {}, None
        )

    monkeypatch.setattr(urllib.request, "urlopen", _open)
    out = monitor_common.probe_live_report(url="https://bob.ntsa.uk/bob/v1/report")
    assert out["status"] == 502
    assert out["doc"] is None
    assert "HTTPError" in out["error"]


def test_summarize_inbound_monitor_fallback_disk_giveup(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (
        f"{ts} #redqueen redqueen-99 "
        "GIVEUP FR SimonBarnett/bobiverse#1 worktree-create-failed:disk"
    )
    it.append_inbound(home, "#redqueen", "redqueen-99", line.split(None, 3)[3])
    summary = it.summarize_inbound_monitor_fallback(home, max_age_sec=3600)
    assert summary["lines"] >= 1
    assert summary["disk_giveups"]


def test_disk_starvation_report_502_attaches_transcript(monkeypatch, tmp_path: Path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    digest.mkdir()
    ear = tmp_path / "bob" / "home"
    ear.mkdir(parents=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    it.append_inbound(
        ear,
        "#redqueen",
        "Jeeves",
        "ACK FR SimonBarnett/bobiverse#10106",
    )

    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "bob"))
    monkeypatch.setenv("BOB_HOME", str(ear))
    monkeypatch.setattr(
        ds,
        "probe_live_report",
        lambda **_k: {"status": 502, "doc": None, "error": "HTTPError:502", "url": "x"},
    )

    class _Args:
        dry_run = False
        chair_home = str(chair)
        digest_home = str(digest)

    payload, code = ds.check(_Args())
    assert code == ds.EXIT_OK
    assert payload.get("soft_ok") is True
    assert payload.get("report_http_status") == 502
    assert payload.get("inbound_transcript")