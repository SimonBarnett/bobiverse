"""MRB #2795 hostile: harvest source.seat from BOB_NICK (#2790 / #2759 gap)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
WORKER_MD = ROOT / "bob" / "docs" / "bob-worker.md"
SCRIPTS = ROOT / "bob" / "scripts"


def _bw():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import bob_worker as bw  # noqa: WPS433

    return bw


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2795_seat_env_extra_exports_matching_nicks(tmp_path: Path):
    bw = _bw()
    nick = "marchhare-32240"
    env = bw.seat_env_extra(tmp_path / "run", "marchhare", nick)
    assert env["BOB_NICK"] == nick
    assert env["BOB_AGENT_NICK"] == nick
    assert env["BOB_NICK"] == env["BOB_AGENT_NICK"]
    assert env["BOB_OUTBOX"].endswith("outbox.txt")
    assert env["BOB_SHOP"] == "#marchhare"


def test_mrb2795_prepare_seat_child_env_keeps_agent_nick_alias(tmp_path: Path):
    """Post-merge scrub must not drop BOB_AGENT_NICK from seat_env_extra."""
    bw = _bw()
    nick = "ionos-99"
    extra = bw.seat_env_extra(tmp_path / "run", "ionos", nick)
    merged = bw.prepare_seat_child_env({"PATH": "C:\\Windows"}, extra)
    assert merged["BOB_NICK"] == nick
    assert merged["BOB_AGENT_NICK"] == nick
    # Hostile: agent-host prefixes still scrubbed
    hostile = bw.prepare_seat_child_env(
        {"PATH": "C:\\Windows"},
        {**extra, "CURSOR_API_KEY": "nope", "SAND_TOKEN": "nope"},
    )
    assert "CURSOR_API_KEY" not in hostile
    assert "SAND_TOKEN" not in hostile
    assert hostile["BOB_AGENT_NICK"] == nick


def test_mrb2795_harvest_ps1_prefers_bob_nick_before_agent_nick():
    text = _utf8_no_bom(HARVEST_PS1)
    assert "FR #2790" in text
    # Contiguous preference block: BOB_NICK first, then elseif BOB_AGENT_NICK
    idx = text.index("FR #2790")
    window = text[idx : idx + 900]
    assert "$env:BOB_NICK" in window
    assert "$env:BOB_AGENT_NICK" in window
    nick_assign = window.index("if ($env:BOB_NICK")
    agent_assign = window.index("elseif ($env:BOB_AGENT_NICK")
    assert nick_assign < agent_assign
    assert "seatNick" in window
    compact = window.replace(" ", "").replace("\r", "")
    assert "seat=$seatNick" in compact


def test_mrb2795_bob_worker_docs_list_agent_nick_alias():
    text = _utf8_no_bom(WORKER_MD)
    assert "BOB_AGENT_NICK" in text
    idx = text.index("BOB_AGENT_NICK")
    window = text[max(0, idx - 80) : idx + 120]
    assert "2790" in window or "FR #2380 / #2790" in text
    assert "source.seat" in text or "harvest" in window.lower()


def test_mrb2795_empty_nick_exports_empty_alias(tmp_path: Path):
    bw = _bw()
    env = bw.seat_env_extra(tmp_path / "run", "m", "  ")
    assert env["BOB_NICK"] == ""
    assert env["BOB_AGENT_NICK"] == ""
