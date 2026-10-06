"""FR #2174: listenable/controllable Bob ear — Start-Bob paths, docs, filter bridge."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

BOB = ROOT / "bob"
COMMON = ROOT / "common"
START = BOB / "scripts" / "Start-Bob.ps1"
DOC = BOB / "docs" / "bob-ear.md"
SKILL = BOB / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"
CMD_SKILL = BOB / ".grok" / "skills" / "bobiverse-bob-commands" / "SKILL.md"
IRC_AGENT = COMMON / "scripts" / "irc_agent.py"
INBOUND = COMMON / "scripts" / "inbound_transcript.py"
WORKER = BOB / "scripts" / "bob_worker.py"

sys.path.insert(0, str(COMMON / "scripts"))
sys.path.insert(0, str(BOB / "scripts"))

import inbound_transcript as it  # noqa: E402
import bob_worker as bw  # noqa: E402


def test_inbound_transcript_module_shipped():
    assert INBOUND.is_file()
    assert "FR #2174" in INBOUND.read_text(encoding="utf-8")


def test_irc_agent_always_appends_inbound_transcript():
    src = IRC_AGENT.read_text(encoding="utf-8")
    assert "inbound_transcript" in src
    assert "append_inbound" in src
    # Raw debug dump stays gated (FR #2351 open_debug_log); scrubbed transcript must not require BOB_IRC_DEBUG.
    assert "open_debug_log" in src and "BOB_IRC_DEBUG" in src
    assert "self.debug = open_debug_log(self.home, enabled=dbg_on)" in src
    # handle_privmsg must call append_inbound before early returns that skip chat.
    i = src.index("def handle_privmsg")
    body = src[i : src.index("\n    def ", i + 10)]
    assert "append_inbound" in body
    assert body.index("append_inbound") < body.index("if not to_channel and not to_me")


def test_start_bob_channel_list_matches_helper_for_fleet_machines():
    t = START.read_text(encoding="utf-8-sig")
    assert '$channel = "#bobiverse,$shop"' in t
    assert "$shop = \"#$MachineId\"" in t or "$shop = \"#$MachineId\"" in t.replace("'", '"')
    for mid in it.FLEET_EAR_MACHINES:
        assert it.channel_list_for_machine(mid) == f"#bobiverse,#{mid}"


def test_docs_describe_listen_and_identical_outbox():
    doc = DOC.read_text(encoding="utf-8")
    assert "inbound-transcript.log" in doc
    assert "FR #2174" in doc
    assert "PRIVMSG <target> :<text>" in doc or "PRIVMSG {target} :<text>" in doc or "PRIVMSG" in doc
    assert "outbox.txt" in doc
    # Verify block should read the scrubbed transcript (not only debug irc.log).
    assert "inbound-transcript.log" in doc.split("## Verify", 1)[-1]


def test_skills_describe_listen_and_send():
    sk = SKILL.read_text(encoding="utf-8")
    assert "inbound-transcript.log" in sk
    assert "FR #2174" in sk
    cmd = CMD_SKILL.read_text(encoding="utf-8")
    assert "inbound-transcript.log" in cmd
    assert "outbox.txt" in cmd
    assert "PRIVMSG" in cmd


@pytest.mark.parametrize(
    "src,target,text,ok",
    [
        ("Jeeves", "#marchhare", "marchhare-4242: FR o/r#1 https://x", True),
        ("marchhare-3556", "#marchhare", "ACK FR o/r#1", False),
        ("Bob-marchhare", "#marchhare", "marchhare-4242: hi", False),
        ("Jeeves", "#marchhare", "chatter for everyone", False),
        ("Jeeves", "marchhare-4242", "private assignment", True),
    ],
)
def test_ear_privmsg_to_worker_filter_accept_and_drop(tmp_path, src, target, text, ok):
    """PRIVMSG shape the ear would see → transcript + bob_worker filter verdict."""
    own = "marchhare-4242"
    # Transcript channel column: shop for channel lines; for PMs still record the PM target.
    transcript_ch = target if target.startswith("#") else target
    got = it.record_ear_to_worker(
        tmp_path,
        channel=transcript_ch,
        nick=src,
        text=text,
        own_nick=own,
        filter_target=target,
        accept_fn=bw.accept_for_agent,
    )
    assert (got["verdict"] == "accept") is ok
    assert bw.accept_for_agent(src, target, text, own) is ok
    body = Path(got["transcript"]).read_text(encoding="utf-8")
    assert src in body
    assert "password=" not in body or "[redacted]" in body
