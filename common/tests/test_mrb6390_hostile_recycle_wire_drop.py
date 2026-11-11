"""MRB #6390 hostile: drop-log must not raise; ear dispatch consumes RECYCLE v1."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import bob_recycle
import bobreport
import irc_agent
import registered_machines as rm
from test_fr6389_recycle_wire_drop_log import CHANS, FakeEar, _patch_info


def test_mrb6390_drop_survives_digest_chair_nick_raise(tmp_path, monkeypatch):
    """Corrupt / raising digest_chair_nick must still log the drop (CodeRabbit #6390)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_CHAIR_NICK", raising=False)
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "win-mpre8vi4u6u")
    rm.sync_from_chanserv(tmp_path, CHANS)
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    bobreport.save_digest(tmp_path, {"chairNick": "Jeeves", "machines": {}})

    ear = FakeEar(tmp_path)
    _patch_info(ear, monkeypatch)

    def boom(_home):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

    monkeypatch.setattr(bobreport, "digest_chair_nick", boom)
    # Drop before accept-path chair compare still uses guarded _chair_disp.
    ok = ear._maybe_execute_recycle_wire("jeeves", "RECYCLE v1 flamingo")
    assert ok is False
    assert ear.recycled == []
    hits = [m for m in ear.logs if "recycle wire dropped" in m and "reason=machine_mismatch" in m]
    assert hits, ear.logs
    assert "chair=-" in hits[0]
    ear.logs.clear()
    # Accept-path chair lookup: raise => chair_missing drop (not an uncaught abort).
    ok2 = ear._maybe_execute_recycle_wire("jeeves", "RECYCLE v1 marchhare")
    assert ok2 is False
    hits2 = [m for m in ear.logs if "recycle wire dropped" in m and "reason=chair_missing" in m]
    assert hits2, ear.logs


def test_mrb6390_ear_handle_privmsg_consumes_recycle_wire(tmp_path, monkeypatch):
    """Wire must reach execute_local_recycle via Client.handle_privmsg, not only the helper."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_CHAIR_NICK", raising=False)
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "win-mpre8vi4u6u")
    rm.sync_from_chanserv(tmp_path, CHANS)
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    bobreport.save_digest(tmp_path, {"chairNick": "Jeeves", "machines": {}})

    class DispatchEar(FakeEar):
        def __init__(self, home: Path):
            super().__init__(home)
            self.channels = list(CHANS)
            self.sent = []
            self._digest_asm = SimpleNamespace(feed=lambda s, b: None)

        def send(self, line):
            self.sent.append(line)

        def _joined_channel(self, t):
            return (t or "").lower() in {c.lower() for c in self.channels}

        def _mine_nicks(self):
            return {(self.original_nick or "").lower()}

        def _note_call_channel(self, t):
            pass

        def _maybe_channel_pong(self, *a, **k):
            return False

        def _maybe_chair_commands(self, *a, **k):
            return False

        def _maybe_git_list(self, *a, **k):
            return False

        def _maybe_git_help(self, *a, **k):
            return False

        def _maybe_assign(self, *a, **k):
            return False

        def _maybe_cleargiveup(self, *a, **k):
            return False

        # FR #6407 / #6628: handle_privmsg dispatches pin/unpin before recycle wire.
        def _maybe_unpin(self, *a, **k):
            return False

        def _maybe_pin(self, *a, **k):
            return False

        def _maybe_focus_ignore(self, *a, **k):
            return False

        def _maybe_shop_listen(self, *a, **k):
            return False

        def _maybe_git_claim(self, *a, **k):
            return False

        def _mark_pm_open(self, n):
            pass

        def _maybe_startworker(self, *a, **k):
            return False

        def _maybe_recycleseat(self, *a, **k):
            return False

        def _handle_build_command(self, *a, **k):
            return None

        def _handle_installtest_command(self, *a, **k):
            return None

        def _handle_register_command(self, *a, **k):
            return False

        def _handle_unregister_command(self, *a, **k):
            return False

        def _handle_bob_local_recycle_command(self, *a, **k):
            raise AssertionError("!recycle parser must not consume RECYCLE v1")

        def _maybe_consume_installtest_v1_wire(self, *a, **k):
            return False

        def _maybe_consume_build_v1_wire(self, *a, **k):
            return False

        # FR #6491 / #6628: later handle_privmsg dispatches before recycle wire.
        def _maybe_consume_build_preflight_wire(self, *a, **k):
            return False

        def _maybe_release_chair_build_lock_on_result(self, *a, **k):
            return False

        def _is_briefer(self):
            return False

        handle_privmsg = irc_agent.Client.handle_privmsg

    ear = DispatchEar(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        bob_recycle,
        "execute_local_recycle",
        lambda mid, home, **k: calls.append(mid),
    )
    monkeypatch.setattr(irc_agent, "info", lambda m: ear.logs.append(m))
    # inbound transcript / other side effects
    monkeypatch.setattr(
        "inbound_transcript.append_inbound",
        lambda *a, **k: None,
        raising=False,
    )

    irc_agent.Client.handle_privmsg(ear, "jeeves", "#bobiverse", "RECYCLE v1 marchhare")
    assert calls == ["marchhare"], ear.logs
    assert ear.announced == ["recycle"]
    assert any("recycle wire accepted" in m for m in ear.logs)
    assert not any("recycle wire dropped" in m for m in ear.logs)


def test_mrb6390_dispatch_ear_binds_pin_unpin_and_build_preflight():
    """FR #6628: FakeEar dispatch stubs must cover every _maybe_* before recycle wire."""
    here = Path(__file__).read_text(encoding="utf-8")
    for needle in (
        "_maybe_unpin",
        "_maybe_pin",
        "_maybe_consume_build_preflight_wire",
        "_maybe_release_chair_build_lock_on_result",
    ):
        assert needle in here
    e2e = Path(__file__).resolve().parent / "test_fr6389_recycle_wire_drop_log.py"
    text = e2e.read_text(encoding="utf-8")
    assert '"_maybe_unpin"' in text or "'_maybe_unpin'" in text
    assert '"_maybe_pin"' in text or "'_maybe_pin'" in text
    assert "_maybe_consume_build_preflight_wire" in text
    assert "_maybe_release_chair_build_lock_on_result" in text
