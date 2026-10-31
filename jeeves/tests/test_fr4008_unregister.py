"""FR #4008: !unregister mirror of !register (+o/+h gate, dry-run/confirm, core refuse)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))

import registered_machines as rm  # noqa: E402
import unregister_cmd as uc  # noqa: E402
import chair_commands as cc  # noqa: E402


def test_parse_unregister_variants():
    assert rm.parse_unregister_command("!unregister ionos")["mid"] == "ionos"
    assert rm.parse_unregister_command("!unregister #IONOS")["mid"] == "ionos"
    assert rm.parse_unregister_command("!unregister dry-run ionos")["dry_run"] is True
    assert rm.parse_unregister_command("!unregister ionos confirm")["confirm"] is True
    assert rm.parse_unregister_command("!register ionos") is None
    assert rm.parse_unregister_command("!unregister")["mid"] is None
    assert rm.parse_unregister_command("!unregister " + ("x" * 80))["mid"] is None


def test_core_channel_refuse():
    assert rm.is_core_unregister_refused("bobiverse")
    assert rm.is_core_unregister_refused("#wonderland")
    assert not rm.is_core_unregister_refused("ionos")


def test_remove_registered_drops_channel(tmp_path: Path):
    rm.save_registered(
        tmp_path,
        {"ionos", "flamingo"},
        source=rm.SOURCE_REGISTER,
        channels=["#bobiverse", "#ionos", "#flamingo", "#wonderland"],
    )
    assert rm.remove_registered(tmp_path, "ionos") == "ionos"
    assert rm.load_registered(tmp_path) == {"flamingo"}
    doc = rm._read_doc(tmp_path)
    chans = [str(c).lower() for c in (doc.get("channels") or [])]
    assert "#ionos" not in chans
    assert "#bobiverse" in chans
    assert doc.get("source") == rm.SOURCE_UNREGISTER


def test_gate_op_halfop_plain():
    members = {
        "#bobiverse": {
            "alice": {"nick": "alice", "modes": {"o"}},
            "bob": {"nick": "bob", "modes": {"h"}},
            "carol": {"nick": "carol", "modes": {"v"}},
            "dave": {"nick": "dave", "modes": set()},
        }
    }
    assert uc.gate_register_unregister(nick="alice", members=members).ok
    assert uc.gate_register_unregister(nick="bob", members=members).ok
    assert not uc.gate_register_unregister(nick="carol", members=members).ok
    assert not uc.gate_register_unregister(nick="dave", members=members).ok
    assert not uc.gate_register_unregister(nick="eve", members=members).ok


def test_operators_txt_ignored_for_gate():
    # Even if we imagined operators.txt listing carol, gate uses modes only.
    members = {"#bobiverse": {"carol": {"nick": "carol", "modes": set()}}}
    assert not uc.gate_register_unregister(nick="carol", members=members).ok


def test_build_plan_dry_run_and_idempotent(tmp_path: Path):
    rm.add_registered(tmp_path, "ionos")
    plan = uc.build_unregister_plan(
        tmp_path, {"mid": "ionos", "dry_run": True, "confirm": False}, asker="simon"
    )
    assert plan and plan.in_registry and plan.dry_run
    assert "UNREGISTER #ionos" in plan.chanserv_line
    assert "UNREGISTERED v1 ionos" in plan.wire_line
    empty = uc.build_unregister_plan(
        tmp_path, {"mid": "missing", "dry_run": False, "confirm": False}, asker="simon"
    )
    assert empty and not empty.in_registry
    assert "not registered" in empty.notes[0]


def test_build_plan_core_refused(tmp_path: Path):
    plan = uc.build_unregister_plan(
        tmp_path, {"mid": "bobiverse", "dry_run": False, "confirm": True}, asker="x"
    )
    assert plan and plan.core_refused


def test_chanserv_confirm_parse():
    assert uc.parse_chanserv_unregister_confirm(
        "To confirm, type: /cs UNREGISTER #ionos Ab12Cd"
    ) == ("#ionos", "Ab12Cd")
    assert uc.parse_chanserv_unregister_confirm("hello") is None


def test_pending_store_ttl():
    now = {"t": 100.0}
    store = uc.PendingUnregisterStore(ttl_s=60.0, now=lambda: now["t"])
    store.put("ionos", "simon")
    assert store.get("ionos") is not None
    now["t"] = 161.0
    assert store.get("ionos") is None


def test_help_registry_has_register_unregister():
    names = {c.name for c in cc.COMMANDS}
    assert "register" in names and "unregister" in names
    cc.validate_registry()


class _FakePriv:
    def __init__(self, members):
        self.state = SimpleNamespace(members=members)


class _FakeArgs:
    chair = True


def _make_agent(tmp_path, members):
    import irc_agent as ia

    sent = []
    whispers = []

    class A(ia.Client if hasattr(ia, "Client") else object):
        pass

    # Prefer constructing minimal stub matching handler expectations
    agent = SimpleNamespace(
        args=_FakeArgs(),
        home=str(tmp_path),
        channels=["#bobiverse", "#ionos"],
        _unregister_pending=uc.PendingUnregisterStore(),
        _cs_unregister_wait={},
        _cs_register_wait={},
        _cs_force=False,
        _privs_engine=_FakePriv(members),
        _mine_nicks=lambda: {"jeeves"},
        _digest_home=lambda: tmp_path,
        send=lambda line: sent.append(line),
        whisper=lambda who, msg: whispers.append((who, msg)),
    )
    # Bind methods from real Client if available
    from irc_agent import Client

    agent._nick_modes_in_channel = Client._nick_modes_in_channel.__get__(agent, Client)
    agent._register_gate_allowed = Client._register_gate_allowed.__get__(agent, Client)
    agent._handle_register_command = Client._handle_register_command.__get__(agent, Client)
    agent._handle_unregister_command = Client._handle_unregister_command.__get__(agent, Client)
    return agent, sent, whispers


def test_handler_gate_denied(tmp_path: Path):
    members = {"#bobiverse": {"nobody": {"nick": "nobody", "modes": set()}}}
    agent, sent, whispers = _make_agent(tmp_path, members)
    assert agent._handle_unregister_command("nobody", "!unregister ionos") is True
    assert sent == []
    assert any("denied" in m and "+o/+h" in m for _, m in whispers)


def test_fakechair_stubs_unregister_dispatch():
    """MRB #4034: FakeChair must stub unregister (and build) or chair_commands_020 AttributeErrors."""
    text = (ROOT / "jeeves" / "tests" / "test_chair_commands_020.py").read_text(encoding="utf-8-sig")
    assert "def _handle_unregister_command" in text
    assert "def _handle_build_command" in text


def test_handler_op_dry_run_no_send(tmp_path: Path):
    rm.add_registered(tmp_path, "ionos")
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, whispers = _make_agent(tmp_path, members)
    assert agent._handle_unregister_command("simon", "!unregister dry-run ionos") is True
    assert sent == []
    assert any("DRY-RUN" in m for _, m in whispers)


def test_handler_confirm_flow_executes(tmp_path: Path, monkeypatch):
    rm.add_registered(tmp_path, "ionos")
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"h"}}}}
    agent, sent, whispers = _make_agent(tmp_path, members)
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    assert agent._handle_unregister_command("simon", "!unregister ionos") is True
    assert sent == []  # plan only
    assert agent._handle_unregister_command("simon", "!unregister ionos confirm") is True
    assert any(x.startswith("PRIVMSG ChanServ :UNREGISTER #ionos") for x in sent)
    assert any(x.startswith("PART #ionos") for x in sent)
    assert any("UNREGISTERED v1 ionos" in x for x in sent)
    assert not rm.is_registered(tmp_path, "ionos")
    assert agent._cs_force is True
    assert any(m.startswith("ACK unregistered") for _, m in whispers)


def test_handler_idempotent_not_registered(tmp_path: Path):
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, whispers = _make_agent(tmp_path, members)
    assert agent._handle_unregister_command("simon", "!unregister missingbox") is True
    assert sent == []
    assert any("not registered" in m for _, m in whispers)


def test_handler_core_refused_no_send(tmp_path: Path):
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, whispers = _make_agent(tmp_path, members)
    assert agent._handle_unregister_command("simon", "!unregister bobiverse") is True
    assert sent == []
    assert any("core channel" in m for _, m in whispers)


def test_register_gate_uses_modes_not_operators_txt(tmp_path: Path, monkeypatch):
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": set()}}}
    agent, sent, whispers = _make_agent(tmp_path, members)
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    # plain user denied even if named simon
    assert agent._handle_register_command("simon", "!register newt") is True
    assert sent == []
    assert any("denied" in m for _, m in whispers)
    # op allowed
    agent._privs_engine.state.members["#bobiverse"]["simon"]["modes"] = {"o"}
    whispers.clear()
    sent.clear()
    assert agent._handle_register_command("simon", "!register newt") is True
    assert any("REGISTER #newt" in x for x in sent)


def test_fr5161_stale_list_does_not_readd_tombstoned_shop(tmp_path: Path):
    """FR #5161: ChanServ LIST still showing a just-unregistered shop must not re-add it."""
    rm.save_registered(
        tmp_path,
        {"ionos", "flamingo"},
        source=rm.SOURCE_REGISTER,
        channels=["#bobiverse", "#ionos", "#flamingo", "#wonderland"],
    )
    assert rm.remove_registered(tmp_path, "ionos") == "ionos"
    assert "ionos" in rm.load_unregister_tombstones(tmp_path)
    res = rm.sync_from_chanserv(
        tmp_path,
        ["#bobiverse", "#ionos", "#flamingo", "#wonderland"],
        now=2000.0,
    )
    assert res is not None
    added, _removed = res
    assert "ionos" not in added
    assert "ionos" not in rm.load_registered(tmp_path)
    chans = [c.lower() for c in rm.load_registered_channels(tmp_path)]
    assert "#ionos" not in chans
    assert "ionos" in rm.load_unregister_tombstones(tmp_path)

    later = rm.sync_from_chanserv(
        tmp_path,
        ["#bobiverse", "#flamingo", "#wonderland"],
        now=2100.0,
    )
    assert later is not None
    assert "ionos" not in rm.load_registered(tmp_path)
    assert "ionos" not in rm.load_unregister_tombstones(tmp_path)


def test_fr5161_stale_list_does_not_rejoin(tmp_path: Path, monkeypatch):
    import irc_agent as ia

    monkeypatch.setattr(ia, "FLOOD_S", 0.0)
    rm.save_registered(
        tmp_path,
        {"ionos", "flamingo"},
        source=rm.SOURCE_REGISTER,
        channels=["#bobiverse", "#ionos", "#flamingo"],
    )
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, _whispers = _make_agent(tmp_path, members)
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    assert agent._handle_unregister_command("simon", "!unregister ionos") is True
    assert agent._handle_unregister_command("simon", "!unregister ionos confirm") is True
    sent.clear()
    ia.Client._apply_chanserv_channels(
        agent,
        ["#bobiverse", "#ionos", "#flamingo"],
    )
    assert not any(x.upper().startswith("JOIN #IONOS") for x in sent)
    assert "ionos" not in rm.load_registered(tmp_path)
    assert "#ionos" not in [c.lower() for c in agent.channels]


def test_fr5161_help_and_skill_pin_tombstone():
    help_text = cc.help_text("unregister") if hasattr(cc, "help_text") else ""
    src = (ROOT / "common" / "scripts" / "chair_commands.py").read_text(encoding="utf-8")
    skill = (ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-commands" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    blob = src + "\n" + skill + "\n" + str(help_text)
    assert "FR #5161" in blob
    assert "tombstone" in blob.lower() or "lagging" in blob.lower()
