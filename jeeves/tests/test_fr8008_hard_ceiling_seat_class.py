"""FR #8008: repeated hard-ceiling GIVEUPs block the same agent seat class."""
from __future__ import annotations

import time
from pathlib import Path

import gitclaim
import shop_listen


REPO = "SimonBarnett/bobiverse"
OC_A = "redqueen-5564"
OC_B = "redqueen-6904"
GROK = "flamingo-17916"


def _home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(gitclaim, "GIVEUP_NEEDS_HUMAN_COUNT", 2)
    return home


def _accept(doc: dict, nick: str) -> dict:
    row = dict(doc["unaccepted"].pop(0))
    row["nick"] = nick
    row["accepted_ts"] = gitclaim._utc_now()
    doc.setdefault("accepted", []).append(row)
    return doc


def test_is_hard_ceiling_reason():
    assert gitclaim.is_hard_ceiling_reason("hard ceiling 1800000ms")
    assert gitclaim.is_hard_ceiling_reason(
        "hard ceiling 1800000ms; last progress 2026-11-17T12:00:00Z; stall 1800123ms"
    )
    assert not gitclaim.is_hard_ceiling_reason("watchdog timeout (no output)")
    assert not gitclaim.is_hard_ceiling_reason("out-of-fuel")


def test_two_hard_ceiling_giveups_stamp_opencode_class(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    # Digest marks both redqueen seats as opencode; flamingo as grok.
    digest = home / "digest.json"
    digest.write_text(
        '{"machines":{"redqueen":{"workers":{'
        '"redqueen-5564":{"kind":"opencode","agent":"opencode"},'
        '"redqueen-6904":{"kind":"opencode","agent":"opencode"}'
        '},"flamingo":{"workers":{'
        '"flamingo-17916":{"kind":"grok","agent":"grok"}'
        '}}}}',
        encoding="utf-8",
    )
    # seat_agent_kind reads bobreport digest shape — stub it.
    monkeypatch.setattr(gitclaim, "seat_agent_kind", lambda _h, nick: (
        "opencode" if "redqueen" in (nick or "").lower() else "grok"
    ))

    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#8008",
        "nick": OC_A,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/issues/8008",
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    reason = "hard ceiling 1800000ms; last progress 2026-11-17T12:00:00Z; stall 1800000ms"
    for seat in (OC_A, OC_B):
        doc = gitclaim._load_queue_unlocked(home)
        # move from unaccepted back to accepted between rounds
        if doc.get("unaccepted"):
            doc = _accept(doc, seat)
        else:
            doc["accepted"][0]["nick"] = seat
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        st, job = shop_listen.return_job_to_unaccepted(
            home,
            repo=REPO,
            task="FR",
            ident="#8008",
            now=time.time(),
            reason=reason,
            expected_nick=seat,
        )
        assert st == "ok" and job is not None

    final = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#8008"][0]
    # FR #8375: hard-ceiling does not burn giveup_count or stamp needs_human.
    assert int(final.get("giveup_count") or 0) == 0
    assert not final.get("needs_human")
    assert int(final.get("hard_ceiling_count") or 0) == 2
    kinds = gitclaim.giveup_agent_kinds(final)
    assert "opencode" in kinds
    assert gitclaim.row_blocked_for_giveup_agent_kind(final, "opencode") is True
    assert gitclaim.row_blocked_for_giveup_agent_kind(final, "grok") is False


def test_one_hard_ceiling_does_not_block_class_yet(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    monkeypatch.setattr(gitclaim, "seat_agent_kind", lambda _h, nick: "opencode")
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#8008",
        "nick": OC_A,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/issues/8008",
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    st, job = shop_listen.return_job_to_unaccepted(
        home,
        repo=REPO,
        task="FR",
        ident="#8008",
        now=time.time(),
        reason="hard ceiling 1800000ms; last progress 2026-11-17T12:00:00Z; stall 1800000ms",
        expected_nick=OC_A,
    )
    assert st == "ok" and job is not None
    assert int(job.get("hard_ceiling_count") or 0) == 1
    assert "opencode" not in gitclaim.giveup_agent_kinds(job)
    assert gitclaim.row_blocked_for_giveup_agent_kind(job, "opencode") is False
