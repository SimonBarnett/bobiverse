"""MRB #3840 hostile pins for FR #3834 wonderland control channel (merged PR #3840)."""
from __future__ import annotations

from pathlib import Path

import bobreport
import chan_privs as cp
import registered_machines as rm
from repo_layout import ROOT

SERVICE = ROOT / "airc/scripts/airc_console_service.py"
AIRC = ROOT / "airc/scripts/airc_console.py"
CHAN_PRIVS = ROOT / "common/scripts/chan_privs.py"
DOCS = ROOT / "jeeves/docs/channel-privileges-and-workers.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def test_hostile_channels_for_nick_ear_vs_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare", "#wonderland"], now=1.0)
    bobreport._SEAT_ROSTER_CACHE["key"] = None  # force re-read registry
    ear = bobreport.channels_for_nick("bob-marchhare", "#bobiverse,#marchhare")
    assert bobreport.WONDERLAND_CHANNEL in ear
    assert "#bobiverse" in ear and "#marchhare" in ear
    # Seat nick {machine}-{pid} — shop only (never wonderland / fleet).
    seat = bobreport.channels_for_nick(
        "marchhare-960", "#bobiverse,#wonderland,#marchhare"
    )
    assert seat == ["#marchhare"]
    assert bobreport.WONDERLAND_CHANNEL not in seat
    # Legacy w-* worker short form — shop only.
    assert bobreport.WONDERLAND_CHANNEL not in bobreport.channels_for_nick(
        "w-mh-1234", "#bobiverse,#wonderland"
    )


def test_hostile_wonderland_not_digest_machine(tmp_path):
    rm.sync_from_chanserv(
        tmp_path, ["#bobiverse", "#wonderland", "#flamingo"], now=1.0
    )
    assert "wonderland" not in rm.load_registered(tmp_path)
    assert "flamingo" in rm.load_registered(tmp_path)
    chans = bobreport.chair_channels(tmp_path)
    assert "#wonderland" in chans
    assert "#flamingo" in chans


def test_hostile_console_and_worker_never_opped_in_wonderland(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(
        tmp_path, ["#bobiverse", "#wonderland", "#marchhare"], now=1.0
    )
    sent, logs, t = [], [], [1000.0]
    eng = cp.ChanPrivEngine(
        send=sent.append,
        log=logs.append,
        now=lambda: t[0],
        me=lambda: "Jeeves",
        channels=lambda: ["#wonderland"],
        is_registered=lambda mid: rm.is_registered(tmp_path, mid),
        normalize=bobreport.normalize_machine_id,
        chan_op=lambda ch: True,
        accounts={"simon"},
    )
    eng.on_line(
        "353",
        ["353", "Jeeves", "=", "#wonderland"],
        "@Jeeves marchhare_console marchhare-960 bob-evil",
        "srv",
        None,
    )
    eng.on_line(
        "366", ["366", "Jeeves", "#wonderland"], "End of /NAMES list.", "srv", None
    )
    modes = [s for s in sent if s.startswith(("MODE", "SAMODE"))]
    assert modes == []


def test_hostile_bob_ear_ops_wonderland_behavioral(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(
        tmp_path, ["#bobiverse", "#wonderland", "#marchhare"], now=1.0
    )
    sent, logs, t = [], [], [1000.0]
    eng = cp.ChanPrivEngine(
        send=sent.append,
        log=logs.append,
        now=lambda: t[0],
        me=lambda: "Jeeves",
        channels=lambda: ["#wonderland"],
        is_registered=lambda mid: rm.is_registered(tmp_path, mid),
        normalize=bobreport.normalize_machine_id,
        chan_op=lambda ch: True,
        accounts={"simon"},
    )
    eng.on_line(
        "353",
        ["353", "Jeeves", "=", "#wonderland"],
        "@Jeeves bob-marchhare",
        "srv",
        None,
    )
    eng.on_line(
        "366", ["366", "Jeeves", "#wonderland"], "End of /NAMES list.", "srv", None
    )
    assert "MODE #wonderland +o bob-marchhare" in sent


def test_hostile_no_domain_control_join_and_timeout_wonderland():
    svc = SERVICE.read_text(encoding="utf-8")
    assert 'self._apply_shop_mode("wonderland")' in svc
    assert "chanserv-probe timeout -> wonderland" in svc
    assert "self.channel = self.domain_channel" not in svc
    assert 'self._apply_shop_mode("domain-lobby")' not in svc
    ac = AIRC.read_text(encoding="utf-8")
    assert "normalize_shop_mode" in ac
    assert 'return "wonderland"' in ac


def test_hostile_docs_flags_setup_for_jeeves():
    docs = DOCS.read_text(encoding="utf-8")
    assert "#wonderland" in docs
    assert "FLAGS #wonderland Jeeves" in docs
    skill = SKILL.read_text(encoding="utf-8")
    assert "#wonderland" in skill
    assert "WONDERLAND_CHANNEL" in CHAN_PRIVS.read_text(encoding="utf-8")
