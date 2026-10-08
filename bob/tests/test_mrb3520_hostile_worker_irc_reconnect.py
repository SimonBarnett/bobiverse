"""MRB #3520 / land #3535 hostile pins for FR #3456 bob-worker IRC reconnect."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
VISION = ROOT / "bob" / "VISION.md"
WORKER = ROOT / "bob" / "scripts" / "bob_worker.py"


def test_mrb3520_vision_and_skill_document_reconnect_grace():
    vision = VISION.read_text(encoding="utf-8")
    assert "bob-worker" in vision.lower()
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3456" in skill
    assert "BOB_WORKER_IRC_RECONNECT_GRACE_S" in skill
    assert "re-ACK" in skill or "re-sends ACK" in skill or "re-send" in skill.lower()
    # Troubleshooting must not claim exit-3 is immediate-by-design after FR #3456.
    assert "grace" in skill.lower()
    assert "Exit 3" in skill
    # Contiguous: exit 3 after grace exhausted (or grace 0), not "soon after start / by design" alone.
    assert "grace exhausted" in skill or "GRACE_S=0" in skill or "legacy" in skill


def test_mrb3520_drain_drops_wrong_target_does_not_hold(tmp_path: Path):
    """Wrong-channel PRIVMSG must not be re-queued on say failure (shop-only rule)."""
    path = tmp_path / "outbox.txt"
    path.write_text(
        "PRIVMSG #bobiverse :DONE FR o/r#1 https://example/p/1\n"
        "PRIVMSG #marchhare :ACK FR o/r#1\n",
        encoding="utf-8",
    )

    class FailSay:
        shop = "#marchhare"

        def say(self, target, text):
            return False

    n = bw.drain_outbox(path, FailSay(), lambda m: None)
    assert n == 0
    body = path.read_text(encoding="utf-8")
    assert "ACK FR o/r#1" in body
    assert "#bobiverse" not in body


def test_mrb3520_prepare_reconnect_clears_socket_and_flags():
    seat = bw.IrcSeat("127.0.0.1", 1, "m-1", "m", tls=False, log=lambda m: None)
    seat.sock = object()  # type: ignore[assignment]
    seat._lost_once = True
    seat._stop.set()
    seat.prepare_reconnect()
    assert seat.sock is None
    assert not seat._lost_once
    assert not seat._stop.is_set()


def test_mrb3520_source_wires_grace_default_and_reack():
    t = WORKER.read_text(encoding="utf-8")
    assert "BOB_WORKER_IRC_RECONNECT_GRACE_S" in t
    assert "_env_float(\"BOB_WORKER_IRC_RECONNECT_GRACE_S\", 600.0" in t or (
        "BOB_WORKER_IRC_RECONNECT_GRACE_S\", 600" in t
    )
    assert "def _on_irc_lost" in t
    assert "def _reconnect_loop" in t
    assert "def _after_irc_reconnect" in t
    assert "re-ACK after reconnect" in t
    assert "prepare_reconnect" in t
