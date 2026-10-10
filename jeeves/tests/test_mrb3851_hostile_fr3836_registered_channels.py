"""MRB #3851 hostile pins for FR #3836: Jeeves joins every registered channel; Bob +o in #wonderland."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import bobreport
import chan_privs as cp
import irc_agent
import registered_machines as rm


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    return tmp_path


def test_hostile_list_exact_channels_no_invented_wonderland(home):
    """When ChanServ LIST omits #wonderland, chair_channels must not invent it."""
    rm.sync_from_chanserv(home, ["#bobiverse", "#flamingo", "#agentic_irc"], now=10.0)
    chans = rm.load_registered_channels(home)
    assert "#agentic_irc" in chans
    assert "#flamingo" in chans
    assert "#wonderland" not in chans
    assert bobreport.chair_channels(home) == chans
    assert "wonderland" not in rm.load_registered(home)


def test_hostile_legacy_synthesize_includes_wonderland(home):
    """No channels[] yet: FR #3834 fallback synthesizes #bobiverse + #wonderland + shops."""
    rm.save_registered(home, {"marchhare"}, source="register-command")
    doc = json.loads(rm.registry_path(home).read_text(encoding="utf-8"))
    assert "channels" not in doc or not doc.get("channels")
    chans = rm.load_registered_channels(home)
    assert chans[:2] == ["#bobiverse", "#wonderland"]
    assert "#marchhare" in chans


def test_hostile_apply_joins_all_registered_paced(home, monkeypatch):
    monkeypatch.setattr(irc_agent, "FLOOD_S", 0.0)
    sleeps = []
    monkeypatch.setattr(irc_agent.time, "sleep", lambda s: sleeps.append(s))
    rm.save_registered(home, {"stale"})
    sent = []
    agent = SimpleNamespace(
        args=SimpleNamespace(chair=True),
        home=home,
        channels=["#bobiverse", "#stale"],
        sent=sent,
        send=sent.append,
        _digest_home=lambda: home,
    )
    irc_agent.Client._apply_chanserv_channels(
        agent, ["#bobiverse", "#flamingo", "#wonderland", "#agentic_irc"]
    )
    assert "JOIN #flamingo" in sent
    assert "JOIN #wonderland" in sent
    assert "JOIN #agentic_irc" in sent
    assert any(s.startswith("PART #stale") for s in sent)
    assert "#stale" not in agent.channels
    assert sleeps, "JOIN/PART path must call time.sleep(FLOOD_S) for pacing"
    src = Path(irc_agent.__file__).read_text(encoding="utf-8")
    apply = src.split("def _apply_chanserv_channels", 1)[1].split(
        "def _handle_register_command", 1
    )[0]
    assert "time.sleep(FLOOD_S)" in apply
    assert "INFO channel-sync registered=" in apply


def test_hostile_bob_plus_o_wonderland_never_console_worker(home):
    rm.sync_from_chanserv(
        home, ["#bobiverse", "#marchhare", "#flamingo", "#wonderland"], now=1.0
    )
    sent, logs = [], []
    ops = {"#wonderland": True, "#bobiverse": True, "#marchhare": True}
    eng = cp.ChanPrivEngine(
        send=sent.append,
        log=logs.append,
        now=lambda: 1000.0,
        me=lambda: "Jeeves",
        channels=lambda: ["#wonderland"],
        is_registered=lambda mid: rm.is_registered(home, mid),
        normalize=bobreport.normalize_machine_id,
        chan_op=lambda ch: ops.get(ch.lower(), False),
        is_oper=lambda: False,
        accounts={"simon"},
    )

    def feed(members: str):
        eng.on_line(
            "353",
            ["353", "Jeeves", "=", "#wonderland", f":{members}"],
            members,
            "srv",
            {},
        )
        eng.on_line(
            "366",
            ["366", "Jeeves", "#wonderland", ":End"],
            "End",
            "srv",
            {},
        )

    feed("@Jeeves bob-marchhare")
    modes = [s for s in sent if s.startswith(("MODE", "SAMODE"))]
    assert "MODE #wonderland +o bob-marchhare" in modes
    assert any(
        ln.startswith("INFO op-grant nick=bob-marchhare channel=#wonderland")
        for ln in logs
    )
    sent.clear()
    feed("@Jeeves marchhare_console marchhare-960 flamingo-101 bob-evil")
    modes2 = [s for s in sent if s.startswith(("MODE", "SAMODE"))]
    assert modes2 == []


def test_hostile_product_fr3836_and_skill_needles():
    root = Path(__file__).resolve().parents[1]
    fr = (root / "tests" / "test_fr3836_jeeves_registered_channels.py").read_text(
        encoding="utf-8"
    )
    assert "test_console_and_worker_never_opped_in_wonderland" in fr
    assert "INFO op-grant nick=" in fr
    assert "JOIN #agentic_irc" in fr
    skill = (
        root / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "wonderland" in skill.lower()
    assert "channel-sync" in skill or "registered channel" in skill.lower()
    # UTF-8 no BOM on product skill
    raw = (root / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
