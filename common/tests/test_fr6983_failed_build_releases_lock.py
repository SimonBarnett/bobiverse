"""FR #6983: failed !build releases chair lock; refused !build replies with reason+id."""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import bobiverse_build as bb
import chair_commands as cc
from repo_layout import ROOT


def test_fr6983_failed_build_then_rebuild_accepted(tmp_path: Path):
    """Acceptance: failed terminal result frees lock; following !build is accepted."""
    who = cc.Principal("ear", "Bob-flamingo", "", "flamingo")
    lock = bb.BuildLock(tmp_path / "build-locks.json", max_parallel=1)
    assert lock.try_acquire("SimonBarnett/bobiverse", "b-1794525453")[0]

    fail = bb.parse_build_result(
        "BUILD fail SimonBarnett/bobiverse version=2.0.0 ref=7f9fc1f8 "
        "blockers=1 pack=False release=False id=b-1794525453"
    )
    assert fail and fail["kind"] == "fail" and fail["id"] == "b-1794525453"
    assert bb.apply_build_result_to_chair_lock(lock, fail) is True
    assert lock.running_id("SimonBarnett/bobiverse") is None

    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.0 47465818",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-next",
    )
    assert dec and dec.ok
    assert lock.running_id("SimonBarnett/bobiverse") == "b-next"


def test_fr6983_ok_build_then_rebuild_accepted(tmp_path: Path):
    """Acceptance: successful terminal result frees lock; following !build is accepted."""
    who = cc.Principal("ear", "Bob-ionos", "", "ionos")
    lock = bb.BuildLock(tmp_path / "l.json", max_parallel=1)
    assert lock.try_acquire("SimonBarnett/bobiverse", "b-ok")[0]

    ok = bb.parse_build_result(
        "BUILD ok SimonBarnett/bobiverse version=2.0.0 ref=main "
        "tag=v2.0.0 prerelease never_latest=True id=b-ok"
    )
    assert ok and ok["kind"] == "ok"
    assert bb.apply_build_result_to_chair_lock(lock, ok) is True
    assert lock.running_id("SimonBarnett/bobiverse") is None

    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.1 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-2",
    )
    assert dec and dec.ok
    assert lock.running_id("SimonBarnett/bobiverse") == "b-2"


def test_fr6983_live_build_refuses_with_reply_lines(tmp_path: Path):
    """Acceptance: genuinely running build refuses; reply names reason + blocking id."""
    who = cc.Principal("ear", "Bob-flamingo", "", "flamingo")
    lock = bb.BuildLock(tmp_path / "l.json", max_parallel=1)
    assert lock.try_acquire("SimonBarnett/bobiverse", "b-live")[0]
    assert lock.touch("SimonBarnett/bobiverse", "b-live") is True

    dec = bb.decide_build(
        who=who,
        body="!build SimonBarnett/bobiverse 2.0.0 main",
        may=cc.may,
        denied_line=cc.denied_line,
        recipe_loader=lambda r: bb.load_recipe(ROOT),
        lock=lock,
        new_build_id=lambda: "b-2",
        dead_max_age_s=1800.0,
        stale_max_age_s=99_000.0,
    )
    assert dec is not None
    assert not dec.ok
    assert dec.reason == "refused"
    assert dec.pm_lines, "refusal must never be silent (empty pm_lines)"
    blob = " ".join(dec.pm_lines)
    assert "refused" in blob
    assert "b-live" in blob
    assert lock.running_id("SimonBarnett/bobiverse") == "b-live"


def test_fr6983_truncated_fail_without_id_still_releases(tmp_path: Path):
    """FR #6983: IRC [:400] can drop trailing id=; terminal fail still frees repo lock."""
    lock = bb.BuildLock(tmp_path / "l.json", max_parallel=1)
    assert lock.try_acquire("SimonBarnett/bobiverse", "b-1794525453")[0]

    # Shape after line[:400] cut mid-blocker URL (id= gone).
    trunc = (
        "BUILD fail SimonBarnett/bobiverse version=2.0.0 ref=7f9fc1f8 blockers=3 "
        "pack=False release=False blocker=https://github.com/SimonBarnett/bobiverse/issue"
    )
    fail = bb.parse_build_result(trunc)
    assert fail is not None
    assert fail["kind"] == "fail"
    assert fail["id"] == ""
    assert bb.apply_build_result_to_chair_lock(lock, fail) is True
    assert lock.running_id("SimonBarnett/bobiverse") is None


def test_fr6983_fail_announce_puts_id_before_blocker_urls():
    """Packaged fail announce must keep id= ahead of long blocker= URLs (IRC 400 cap)."""
    src = (ROOT / "common" / "scripts" / "bobiverse_build.py").read_text(encoding="utf-8")
    assert "FR #6983" in src
    assert "def build_result_id_early" in src
    # Early id helper used on the terminal fail announce path.
    fail_at = src.index("blockers={n} pack={report.pack_ok} release={report.release_ok}")
    early_at = src.rindex("id_early = build_result_id_early", 0, fail_at)
    assert early_at < fail_at
    assert bb.build_result_id_early("b-1") == " id=b-1"
    assert bb.build_result_id_early("") == ""


def test_fr6983_chair_handler_releases_on_fail_and_channel_refusal_reply(
    tmp_path: Path, monkeypatch
):
    """Chair: BUILD fail frees home lock; refused !build addresses the channel sender."""
    import irc_agent as ia

    home = tmp_path / "jeeves-home"
    home.mkdir()
    lock = bb.BuildLock(home / "build-locks.json")
    lock.try_acquire("SimonBarnett/bobiverse", "b-held")

    args = SimpleNamespace(chair=True, home=str(home), nick="Jeeves")
    agent = ia.Client.__new__(ia.Client)
    agent.args = args
    agent.home = str(home)
    agent.original_nick = "Jeeves"
    agent.live_nick = "Jeeves"
    agent.channels = ["#bobiverse"]
    sent: list[str] = []
    whispers: list[tuple[str, str]] = []

    def _send(line: str) -> None:
        sent.append(line)

    def _whisper(nick: str, msg: str) -> None:
        whispers.append((nick, msg))

    monkeypatch.setattr(agent, "send", _send)
    monkeypatch.setattr(agent, "whisper", _whisper)
    monkeypatch.setattr(agent, "_cmd_trace", lambda *a, **k: None)
    monkeypatch.setattr(agent, "_principal", lambda nick: cc.Principal("ear", nick, "", "flamingo"))
    monkeypatch.setattr(agent, "_mine_nicks", lambda: {"jeeves"})
    monkeypatch.setattr(agent, "_install_root", lambda: str(ROOT))
    monkeypatch.setattr(agent, "_whois_hint", lambda nick: None)

    body = (
        "BUILD fail SimonBarnett/bobiverse version=2.0.0 ref=main "
        "blockers=0 pack=False release=False id=b-held"
    )
    assert agent._maybe_release_chair_build_lock_on_result("Bob-flamingo", body) is True
    assert lock.running_id("SimonBarnett/bobiverse") is None

    # Re-hold to exercise refusal reply path.
    lock.try_acquire("SimonBarnett/bobiverse", "b-live")
    lock.touch("SimonBarnett/bobiverse", "b-live")
    agent._handle_build_command(
        "bob-flamingo",
        "!build SimonBarnett/bobiverse 2.0.0 main",
        target="#bobiverse",
        to_channel=True,
    )
    assert any("refused" in m and "b-live" in m for _, m in whispers), whispers
    addressed = [
        s for s in sent if s.upper().startswith("PRIVMSG #BOBIVERSE") and "bob-flamingo:" in s.lower()
    ]
    assert addressed, f"expected addressed channel refusal, sent={sent}"
    assert any("refused" in s and "b-live" in s for s in addressed)
