"""FR #9878: when ear !assign mute / cmd-trace stale, dispatch shop-wire via Jeeves outbox."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))

import shop_wire_assign as sw  # noqa: E402
import intervene_assign as ia  # noqa: E402


def _fixture_idle_offerable():
    return {
        "ok": False,
        "idle_seats": [
            {"machine": "flamingo", "nick": "flamingo-16952", "pid": 16952, "state": "idle"},
            {"machine": "redqueen", "nick": "redqueen-8320", "pid": 8320, "state": "idle"},
        ],
        "offerable_for_live_seats": 2,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#9932",
                "url": "https://github.com/SimonBarnett/bobiverse/pull/9932",
                "mergeable": True,
                "mergeable_state": "CLEAN",
                "title": "MRB clean",
            },
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#9928",
                "url": "https://github.com/SimonBarnett/bobiverse/pull/9928",
                "mergeable": True,
                "title": "MRB 2",
            },
        ],
    }


def test_fr9878_default_chair_outbox_env(tmp_path, monkeypatch):
    target = tmp_path / "jeeves-outbox.txt"
    monkeypatch.setenv("BOB_CHAIR_OUTBOX", str(target))
    assert sw.default_chair_outbox() == target


def test_fr9878_default_chair_outbox_home(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_CHAIR_OUTBOX", raising=False)
    monkeypatch.delenv("JEEVES_HOME", raising=False)
    monkeypatch.delenv("BOB_JEEVES_HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert sw.default_chair_outbox() == tmp_path / ".jeeves" / "outbox.txt"


def test_fr9878_shop_wire_line_format():
    shop, announce = sw.shop_wire_lines(
        nick="flamingo-16952",
        repo="SimonBarnett/bobiverse",
        task="MRB",
        num="9932",
        url="https://github.com/SimonBarnett/bobiverse/pull/9932",
    )
    assert shop == (
        "PRIVMSG #flamingo :flamingo-16952: MRB SimonBarnett/bobiverse#9932 "
        "https://github.com/SimonBarnett/bobiverse/pull/9932"
    )
    assert announce.startswith("PRIVMSG #bobiverse :assign: sent flamingo-16952: MRB ")
    assert "9932" in announce


def test_fr9878_cmd_trace_stale_when_old(tmp_path):
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    trace = chair / "cmd-trace.log"
    trace.write_text("old\n", encoding="utf-8")
    old = time.time() - 600
    import os

    os.utime(trace, (old, old))
    snap = sw.cmd_trace_mute_snapshot(chair, max_age_s=120)
    assert snap["stale"] is True
    assert snap["age_s"] >= 500


def test_fr9878_cmd_trace_fresh_when_recent(tmp_path):
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    (chair / "cmd-trace.log").write_text("fresh\n", encoding="utf-8")
    snap = sw.cmd_trace_mute_snapshot(chair, max_age_s=120)
    assert snap["stale"] is False


def test_fr9878_cmd_trace_missing_is_stale(tmp_path):
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    snap = sw.cmd_trace_mute_snapshot(chair, max_age_s=120)
    assert snap["stale"] is True
    assert snap["reason"] == "missing"


def test_fr9878_shop_wire_intervene_writes_utf8_no_bom(tmp_path):
    report = _fixture_idle_offerable()
    outbox = tmp_path / "outbox.txt"
    payload = sw.intervene_shop_wire_from_report(
        report,
        outbox=outbox,
        dry_run=False,
        pace_s=0,
        offerable_fn=lambda row, nick: True,
    )
    assert payload["written_count"] == 4  # shop + announce per assign
    raw = outbox.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    lines = outbox.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("PRIVMSG #flamingo :flamingo-16952: MRB ")
    assert lines[1].startswith("PRIVMSG #bobiverse :assign: sent ")
    assert "PRIVMSG #redqueen :redqueen-8320: MRB " in lines[2]
    assert all(not ln.startswith("PRIVMSG #bobiverse :!assign") for ln in lines)
    assert payload["mode"] == "shop_wire"


def test_fr9878_prefer_ear_when_cmd_trace_live(tmp_path):
    """When cmd-trace is fresh, intervene path stays on ear !assign (FR #9461)."""
    report = _fixture_idle_offerable()
    ear = tmp_path / "ear-outbox.txt"
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    (chair / "cmd-trace.log").write_text("live\n", encoding="utf-8")
    payload = ia.intervene_from_report(
        report,
        outbox=ear,
        dry_run=False,
        pace_s=0,
        offerable_fn=lambda row, nick: True,
        chair_home=chair,
        prefer_shop_wire_on_mute=True,
        chair_outbox=tmp_path / "jeeves-outbox.txt",
    )
    assert payload["mode"] == "ear_assign"
    text = ear.read_text(encoding="utf-8")
    assert "!assign" in text
    assert not (tmp_path / "jeeves-outbox.txt").exists()


def test_fr9878_fallback_shop_wire_when_cmd_trace_stale(tmp_path):
    report = _fixture_idle_offerable()
    ear = tmp_path / "ear-outbox.txt"
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    trace = chair / "cmd-trace.log"
    trace.write_text("stale\n", encoding="utf-8")
    old = time.time() - 600
    import os

    os.utime(trace, (old, old))
    chair_out = tmp_path / "jeeves-outbox.txt"
    payload = ia.intervene_from_report(
        report,
        outbox=ear,
        dry_run=False,
        pace_s=0,
        offerable_fn=lambda row, nick: True,
        chair_home=chair,
        prefer_shop_wire_on_mute=True,
        chair_outbox=chair_out,
        cmd_trace_mute_s=120,
    )
    assert payload["mode"] == "shop_wire"
    assert payload.get("cmd_trace_mute", {}).get("stale") is True
    assert chair_out.is_file()
    lines = chair_out.read_text(encoding="utf-8").splitlines()
    assert any(ln.startswith("PRIVMSG #flamingo :") for ln in lines)
    assert any(ln.startswith("PRIVMSG #bobiverse :assign: sent ") for ln in lines)
    assert not ear.exists() or "!assign" not in ear.read_text(encoding="utf-8")


def test_fr9878_force_shop_wire_ignores_fresh_trace(tmp_path):
    report = _fixture_idle_offerable()
    chair = tmp_path / ".jeeves"
    chair.mkdir()
    (chair / "cmd-trace.log").write_text("fresh\n", encoding="utf-8")
    chair_out = tmp_path / "outbox.txt"
    payload = ia.intervene_from_report(
        report,
        outbox=tmp_path / "ear.txt",
        dry_run=False,
        pace_s=0,
        offerable_fn=lambda row, nick: True,
        chair_home=chair,
        force_shop_wire=True,
        chair_outbox=chair_out,
    )
    assert payload["mode"] == "shop_wire"
    assert "assign: sent" in chair_out.read_text(encoding="utf-8")


def test_fr9878_send_helper_ps1_exists():
    root = Path(__file__).resolve().parents[1]
    helper = root / "scripts" / "Send-JeevesShopAssign.ps1"
    assert helper.is_file(), "optional helper Send-JeevesShopAssign.ps1 missing"
    text = helper.read_text(encoding="utf-8")
    assert "BOB_CHAIR_OUTBOX" in text
    assert "shop-wire" in text.lower() or "shop_wire" in text.lower() or "PRIVMSG" in text


def test_fr9878_docs_mention_walrus_and_mute():
    root = Path(__file__).resolve().parents[1]
    mon = (root / "docs" / "monitoring.md").read_text(encoding="utf-8")
    assert "9878" in mon
    assert "require_machine=walrus" in mon or "require_machine: walrus" in mon
    skill = (
        root / ".grok" / "skills" / "bobiverse-jeeves-agent-seat-dispatch" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "9878" in skill
    assert "shop-wire" in skill.lower() or "shop_wire" in skill.lower()
