"""FR #6066: Wake-GrokBotBob adapter (mocked send; redacted logs)."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import REPO

sys.path.insert(0, str(REPO / "jeeves" / "tools" / "monitor"))

import wake_grok_bot_bob as wake  # noqa: E402


def test_fr6066_mocked_send_once_brief_has_repo_n():
    calls = []

    def fake_send(*, agent, text):
        calls.append((agent, text))
        return {"ok": True}

    item = {
        "kind": "issue",
        "event": "closed",
        "repo": "SimonBarnett/bobiverse",
        "number": 6066,
    }
    out = wake.wake_bob(item, send=fake_send)
    assert out["ok"] is True
    assert out.get("woke") is True
    assert len(calls) == 1
    assert calls[0][0] == "Bob"
    assert "SimonBarnett/bobiverse#6066" in calls[0][1]
    assert "!assign" not in calls[0][1]


def test_fr6066_unreachable_is_finding():
    def boom(*, agent, text):
        raise ConnectionError("down")

    out = wake.wake_bob(
        {"repo": "SimonBarnett/bobiverse", "number": 1, "event": "merged", "kind": "pr"},
        send=boom,
    )
    assert out["ok"] is False
    assert out.get("error") == "bob_unreachable"


def test_fr6066_mrb_rejects_incomplete_ticket_without_send():
    calls = []

    def fake_send(*, agent, text):
        calls.append((agent, text))
        return {"ok": True}

    out = wake.wake_bob({"repo": "", "number": "", "event": "closed", "kind": "issue"}, send=fake_send)
    assert out["ok"] is False
    assert out.get("error") == "invalid_ticket"
    assert calls == []
    code = wake.main(["--repo", "", "--number", ""])
    assert code == 2
    assert calls == []


def test_fr6066_logs_redact_token_and_sandbox():
    secret = "tok_" + "EN" + "XYZ99"
    sandbox = "https://grok.com/sandbox/" + "sess99"
    raw = f"send fail token={secret} url={sandbox} owner/repo#1"
    red = wake.redact_wake_log(raw)
    assert secret not in red
    assert sandbox not in red
    assert "sandbox" not in red.lower() or "***" in red
    src = Path(wake.__file__).read_text(encoding="utf-8")
    assert "!assign" not in src
    assert (REPO / "jeeves" / "scripts" / "Wake-GrokBotBob.ps1").is_file()
    assert "require_machine" in (REPO / "jeeves" / "docs" / "wake-grok-bot-bob.md").read_text(encoding="utf-8")
