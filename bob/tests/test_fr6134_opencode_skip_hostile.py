"""FR #6134: OpenCode worker NACK hostile MRB/UAT without ACK; digest kind publish."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_opencode_skips_hostile_assign_helpers():
    assert bw.opencode_skips_hostile_assign("opencode", "FROM jeeves #x nick: MRB o/r#1 https://x") is True
    assert bw.opencode_skips_hostile_assign("opencode", "FROM jeeves #x nick: UAT o/r#0 https://x") is True
    assert bw.opencode_skips_hostile_assign("opencode", "FROM jeeves #x nick: FR o/r#2 https://x") is False
    assert bw.opencode_skips_hostile_assign("opencode", "FROM jeeves #x nick: FIX o/r#3 https://x") is False
    assert bw.opencode_skips_hostile_assign("grok", "FROM jeeves #x nick: MRB o/r#1 https://x") is False
    line = bw.opencode_hostile_nack_line("FROM jeeves #x nick: MRB SimonBarnett/bobiverse#6121 https://x")
    assert line == "NACK MRB SimonBarnett/bobiverse#6121 opencode-skips-hostile (FR #6134)"


def test_post_digest_seat_kind_payload(monkeypatch):
    seen = {}

    def fake_post(url, payload, timeout=10.0, log=None):
        seen["url"] = url
        seen["payload"] = payload
        return True

    monkeypatch.setattr(bw, "_http_post_json", fake_post)
    ok = bw.post_digest_seat_kind(
        machine="redqueen",
        pid=9388,
        nick="redqueen-9388",
        kind="opencode",
        model="opencode-go/kimi-k2.7-code",
        url="https://example.test/bob/v1/report",
    )
    assert ok is True
    p = seen["payload"]
    assert p["id"] == "redqueen"
    assert p["pid"] == 9388
    assert p["kind"] == "opencode"
    assert p["nick"] == "redqueen-9388"
    assert "opencode" in str(p.get("agent") or "")

def test_relay_deliver_nacks_hostile_before_ack(tmp_path):
    """FR #6134: OpenCode Relay.deliver NACKS MRB before ACK-on-receipt."""
    outbox = tmp_path / "outbox.txt"
    outbox.write_text("", encoding="utf-8")
    written = []

    def write_outbox(s: str) -> bool:
        written.append(s)
        outbox.write_text((outbox.read_text(encoding="utf-8") + s + "\n"), encoding="utf-8")
        return True

    injected = []
    relay = bw.Relay(log=lambda *_: None, outbox_path=outbox)
    relay.write_outbox = write_outbox
    relay.skips_hostile_assign = lambda line: bw.opencode_skips_hostile_assign("opencode", line)
    relay.set_target(lambda line: injected.append(line) or True)

    status = relay.deliver("jeeves", "#redqueen", "redqueen-1: MRB SimonBarnett/bobiverse#6121 https://x")
    assert status == "opencode_skips_hostile"
    assert injected == []
    assert any(w.startswith("NACK MRB") for w in written)
    assert not any(w.startswith("ACK ") for w in written)

    # FR still injects / ACKs; must not NACK as hostile
    written.clear()
    status2 = relay.deliver("jeeves", "#redqueen", "redqueen-1: FR SimonBarnett/bobiverse#6134 https://x")
    assert status2 == "injected"
    assert injected
    assert not any("opencode-skips-hostile" in w for w in written)


def test_bob_setup_opencode_skill_no_orphan_fr6134():
    """MRB #6135: skill insert must keep 'stronger seat (Grok first' contiguous (harvest #1616)."""
    root = Path(__file__).resolve().parents[1]
    skill = (root / ".grok" / "skills" / "bob-setup-opencode" / "SKILL.md").read_text(encoding="utf-8")
    assert "Hostile MRB stays on a stronger\nseat (Grok first, then Cursor)." in skill
    assert "Chair gate (FR #6134)" in skill
    # orphan continuation after a mid-paragraph insert must not remain
    assert "\n\nseat (Grok first, then Cursor)." not in skill

