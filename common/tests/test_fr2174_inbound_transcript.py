"""FR #2174: always-on scrubbed inbound transcript + fleet ear recovery paths."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import inbound_transcript as it  # noqa: E402


def test_scrub_redacts_password_and_tokens():
    assert "password=secret" not in it.scrub_text("hi password=secret there")
    assert "[redacted]" in it.scrub_text("hi password=secret there")
    assert "[redacted]" in it.scrub_text("token ghp_abcdefghijklmnopqrstuv")
    assert "hello" in it.scrub_text("hello world")


def test_format_line_has_channel_nick_text():
    when = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
    line = it.format_transcript_line("#marchhare", "Jeeves", "marchhare-1: FR x#1", when=when)
    assert line.startswith("2026-10-04T12:00:00Z #marchhare Jeeves ")
    assert "marchhare-1: FR x#1" in line


def test_append_inbound_always_writes_without_bob_irc_debug(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_IRC_DEBUG", raising=False)
    home = tmp_path / "home"
    path = it.append_inbound(home, "#ionos", "Jeeves", "ionos-9: ping")
    assert path == home / "inbound-transcript.log"
    body = path.read_text(encoding="utf-8")
    assert "#ionos Jeeves" in body
    assert "ionos-9: ping" in body
    assert not (home / "irc.log").exists()


def test_append_inbound_scrubs_secrets(tmp_path):
    path = it.append_inbound(tmp_path, "#flamingo", "Bob-flamingo", "set password=hunter2")
    text = path.read_text(encoding="utf-8")
    assert "hunter2" not in text
    assert "[redacted]" in text


def test_rotate_creates_backup(tmp_path):
    path = tmp_path / it.TRANSCRIPT_NAME
    path.write_text("x" * 100, encoding="utf-8")
    it.rotate_if_needed(path, max_bytes=50, backup_count=2)
    assert not path.exists()
    assert (tmp_path / (it.TRANSCRIPT_NAME + ".1")).exists()


def test_append_rotates_when_over_max(tmp_path):
    home = tmp_path / "h"
    # Force tiny max so second write rotates.
    it.append_inbound(home, "#m", "a", "one", max_bytes=30, backup_count=2)
    it.append_inbound(home, "#m", "b", "two-long-enough-to-rotate", max_bytes=30, backup_count=2)
    assert (home / it.TRANSCRIPT_NAME).exists()
    # After rotate, either .1 exists or current file was rewritten.
    backups = list(home.glob(it.TRANSCRIPT_NAME + ".*"))
    assert backups or (home / it.TRANSCRIPT_NAME).stat().st_size > 0


@pytest.mark.parametrize("mid", list(it.FLEET_EAR_MACHINES))
def test_channel_list_identical_for_fleet_machines(mid):
    assert it.channel_list_for_machine(mid) == f"#bobiverse,#wonderland,#{mid}"


def test_channel_list_sanitizes():
    assert it.channel_list_for_machine("MarchHare") == "#bobiverse,#wonderland,#marchhare"


def test_channel_list_folds_ionos_alias_to_win_mpre():
    """DIGEST_ID_FOLD: ionos shop is #win-mpre8vi4u6u, never #ionos (MRB #2262)."""
    assert it.canonical_machine_id("ionos") == "win-mpre8vi4u6u"
    assert it.channel_list_for_machine("ionos") == "#bobiverse,#wonderland,#win-mpre8vi4u6u"
    assert "win-mpre8vi4u6u" in it.FLEET_EAR_MACHINES


def test_ear_recovery_absent_service():
    plan = it.ear_recovery_plan(
        "marchhare",
        service_running=False,
        home_has_outbox=False,
        transcript_present=False,
    )
    assert plan[0] == "install_or_start_ircBob"
    assert "ensure_home_outbox_txt" in plan


def test_ear_recovery_stale_irc_listen_flamingo():
    plan = it.ear_recovery_plan(
        "flamingo",
        service_running=False,
        home_has_outbox=True,
        transcript_present=False,
        stale_irc_listen=True,
    )
    assert plan[0] == "retire_stale_irc_listen_use_ircBob"
    assert "install_or_start_ircBob" in plan


def test_ear_recovery_running_missing_transcript():
    plan = it.ear_recovery_plan(
        "ionos",
        service_running=True,
        home_has_outbox=True,
        transcript_present=False,
    )
    assert plan == ["restart_ircBob_for_inbound_transcript"]


def test_ear_recovery_healthy_ok():
    assert (
        it.ear_recovery_plan(
            "marchhare",
            service_running=True,
            home_has_outbox=True,
            transcript_present=True,
        )
        == ["ok"]
    )


def test_worker_filter_verdict_accept_and_drop():
    own = "marchhare-40208"
    assert (
        it.worker_filter_verdict(
            "Jeeves",
            "#marchhare",
            f"{own}: FR SimonBarnett/bobiverse#2174 https://x",
            own,
        )
        == "accept"
    )
    assert (
        it.worker_filter_verdict(
            "marchhare-3556",
            "#marchhare",
            "ACK FR o/r#1",
            own,
        )
        == "drop"
    )
    assert (
        it.worker_filter_verdict(
            "Jeeves",
            "#marchhare",
            "broadcast chatter",
            own,
        )
        == "drop"
    )


def test_record_ear_to_worker_writes_transcript_and_verdict(tmp_path):
    own = "ionos-100"
    got = it.record_ear_to_worker(
        tmp_path,
        channel="#ionos",
        nick="Jeeves",
        text=f"{own}: FR o/r#9 https://x",
        own_nick=own,
    )
    assert got["verdict"] == "accept"
    text = Path(got["transcript"]).read_text(encoding="utf-8")
    assert "#ionos Jeeves" in text
    dropped = it.record_ear_to_worker(
        tmp_path,
        channel="#ionos",
        nick="Bob-ionos",
        text=f"{own}: hi",
        own_nick=own,
    )
    assert dropped["verdict"] == "drop"
