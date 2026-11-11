"""PR #5852: live-offer suppression on the production bored-latency path.

A missing ``offered_ts`` used to age as ``OFFER_TIMEOUT_S + 1`` (91s).
giveup/done/nack offers stay live for 180s, so those rows looked live on
every scan. ``heal_bored_latency`` also built its detector snapshot without
``unaccepted``, and chair ``_stall_scan`` did not pass the queue rows, so
recycle still fired while the stall finding was hidden.

Expired offers and lost-DONE reoffers to the prior holder must still fire.
A bad timestamp must not reap seat-hold or out-of-fuel marks.
FR #6103: a successful ``!recycleseat`` heal drops the bored-latency finding
before filing (FR #6633: stall_scan asserts empty filed titles on recycle).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import bobreport
import chair_health
import gitclaim
import registered_machines
import stall_detectors as sd
import stall_filer

NOW = 1_700_000_000.0
NICK = "flamingo-37172"
LAG = 400.0


def _iso(age_s: float) -> str:
    return datetime.fromtimestamp(NOW - age_s, timezone.utc).isoformat()


def _offer(**extra) -> dict:
    row = {"offered_to": NICK, "offered_ts": _iso(30)}
    row.update(extra)
    return row


def _snap(*rows: dict) -> dict:
    return {
        "now": NOW,
        "idle": {NICK},
        "last_bored": {NICK: NOW - LAG},
        "unaccepted": list(rows),
    }


def _queue_row(**extra) -> dict:
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#5849",
        "offered_to": NICK,
        "offered_ts": _iso(30),
    }
    row.update(extra)
    return row


def _arm_seat(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [{"nick": NICK, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    gitclaim.record_last_bored(tmp_path, NICK, now=NOW - LAG)
    return install


def _heal(tmp_path, monkeypatch, *rows: dict):
    install = _arm_seat(tmp_path, monkeypatch)
    return gitclaim.heal_bored_latency(
        tmp_path,
        idle={NICK},
        last_bored={NICK: NOW - LAG},
        last_activity={},
        accepted=[],
        unaccepted=list(rows),
        now=NOW,
        install_root=install,
    )


def test_unparseable_offer_age_expires_every_window_and_keeps_seat_marks():
    sentinel = gitclaim._unparseable_offer_age_s()
    assert sentinel > gitclaim.OFFER_TIMEOUT_S + 1.0
    for via in (None, "giveup", "done", "nack"):
        row = {} if via is None else {"offered_via": via}
        assert sentinel >= gitclaim.offer_timeout_s(row)
        assert sentinel < gitclaim.SEAT_HOLD_MAX_S
        assert sentinel < gitclaim.SEAT_OUT_OF_FUEL_MAX_S
    for bad in ("", "   ", "not-a-timestamp", "done", None):
        age = gitclaim._offer_age_s({"offered_ts": bad, "offered_via": "done"}, NOW)
        assert age == sentinel
        assert age >= gitclaim.offer_timeout_s({"offered_via": "done"})
    real = gitclaim._offer_age_s({"offered_ts": _iso(100), "offered_via": "done"}, NOW)
    assert 99.0 <= real <= 101.0
    assert real < gitclaim.offer_timeout_s({"offered_via": "done"})


def test_bad_seat_mark_timestamps_are_not_reaped(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    key = NICK.lower()
    holds = gitclaim._seat_holds_path(tmp_path)
    holds.parent.mkdir(parents=True, exist_ok=True)
    holds.write_text(
        '{"v": 1, "holds": {"%s": {"nick": "%s", "ts": "not-a-timestamp"}}}\n'
        % (key, NICK),
        encoding="utf-8",
    )
    assert key in gitclaim._load_seat_holds_unlocked(tmp_path, NOW)
    fuel = gitclaim._seat_out_of_fuel_path(tmp_path)
    fuel.write_text(
        '{"v": 1, "seats": {"%s": {"nick": "%s", "ts": "", "reason": "out-of-fuel"}}}\n'
        % (key, NICK),
        encoding="utf-8",
    )
    assert key in gitclaim._load_seat_out_of_fuel_unlocked(tmp_path, NOW)


def test_detector_live_expired_lost_done_and_bad_timestamp():
    assert sd.detect_bored_latency(_snap(_offer())) == []
    assert sd.detect_bored_latency(
        _snap(_offer(offered_ts=_iso(gitclaim.offer_timeout_s(_offer()) + 1)))
    )
    assert sd.detect_bored_latency(_snap(_offer(prior_holder=NICK)))
    for via in ("giveup", "done", "nack"):
        assert sd.detect_bored_latency(_snap(_offer(offered_via=via, offered_ts="")))
        assert sd.detect_bored_latency(
            _snap(_offer(offered_via=via, offered_ts="not-a-timestamp"))
        )
        assert (
            sd.detect_bored_latency(_snap(_offer(offered_via=via, offered_ts=_iso(100))))
            == []
        )


def test_offer_to_other_nick_does_not_suppress():
    assert sd.detect_bored_latency(_snap(_offer(offered_to="marchhare-22900")))


@pytest.mark.parametrize(
    ("extra", "recycles"),
    [
        ({}, False),
        ({"offered_ts": _iso(gitclaim.OFFER_TIMEOUT_S + 5)}, True),
        ({"prior_holder": NICK}, True),
        ({"offered_via": "done", "offered_ts": ""}, True),
        ({"offered_via": "giveup", "offered_ts": "bogus"}, True),
        ({"offered_via": "nack", "offered_ts": _iso(100)}, False),
    ],
)
def test_heal_respects_live_offer(tmp_path, monkeypatch, extra, recycles):
    lines = _heal(tmp_path, monkeypatch, _offer(**extra))
    hit = any(f"recycleseat={NICK}" in line for line in lines)
    assert hit is recycles, lines


def test_heal_without_unaccepted_snapshot_still_recycles(tmp_path, monkeypatch):
    """Callers that omit the new argument keep the pre-#5852 snapshot."""
    install = _arm_seat(tmp_path, monkeypatch)
    lines = gitclaim.heal_bored_latency(
        tmp_path,
        idle={NICK},
        last_bored={NICK: NOW - LAG},
        accepted=[],
        now=NOW,
        install_root=install,
    )
    assert any(f"recycleseat={NICK}" in line for line in lines), lines


def _stall_scan(tmp_path, monkeypatch, row: dict):
    _arm_seat(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    filed: list[str] = []

    def _create(title, body):
        filed.append(title)
        return {"number": 1}

    monkeypatch.setattr(stall_filer, "default_create", _create)
    logs: list[str] = []
    jobs = chair_health.ChairJobs(
        tmp_path,
        tmp_path,
        log=logs.append,
        announce=lambda text: None,
        http=lambda *args, **kwargs: 200,
        token_loader=lambda: ("", "none"),
        clock=lambda: NOW,
        sleep=lambda _s: None,
        spawn=False,
    )
    jobs._stall_scan()
    return logs, filed


@pytest.mark.parametrize(
    ("row", "recycles"),
    [
        (_queue_row(), False),
        (_queue_row(offered_ts=_iso(gitclaim.OFFER_TIMEOUT_S + 5)), True),
        (_queue_row(prior_holder=NICK), True),
        (_queue_row(offered_via="done", offered_ts=""), True),
        (_queue_row(offered_via="giveup", offered_ts="bogus"), True),
        (_queue_row(offered_via="nack", offered_ts=_iso(100)), False),
    ],
)
def test_stall_scan_wires_live_offer_suppression(tmp_path, monkeypatch, row, recycles):
    """Live offer suppresses recycle; expired/lost-done still recycle (PR #5852).

    FR #6103 / #6195: when heal queues ``!recycleseat``, ``drop_healed_bored_findings``
    removes the bored-latency finding before the filer. Recycle rows must log the
    heal line and must not open ``stall:bored-latency`` issues.
    """
    logs, filed = _stall_scan(tmp_path, monkeypatch, row)
    text = "\n".join(logs)
    bored_filed = [title for title in filed if title.startswith("stall:bored-latency:")]
    if recycles:
        assert f"bored-latency recycleseat={NICK}" in text, text
        assert bored_filed == [], filed
    else:
        assert "bored-latency" not in text, text
        assert bored_filed == []
