"""FR #5164: stall detectors + filer (dedupe, cap, spool)."""
from __future__ import annotations

from pathlib import Path

import stall_detectors as sd
import stall_filer as sf


def _mrb(url: str, author: str, giveups=()):
    return {
        "task": "MRB",
        "repo": "SimonBarnett/a-search",
        "url": url,
        "title": "MRB",
        "author_seat": author,
        "giveup_seats": ",".join(giveups),
    }


def test_self_review_deadlock_5163_case():
    snap = {
        "live": {"flamingo-67876", "marchhare-22900"},
        "idle": {"flamingo-67876", "marchhare-22900"},
        "unaccepted": [
            _mrb(
                "https://github.com/SimonBarnett/a-search/pull/5294",
                "flamingo-67876",
                ["marchhare-22900"],
            ),
            _mrb(
                "https://github.com/SimonBarnett/a-search/pull/5289",
                "marchhare-22900",
                ["flamingo-67876"],
            ),
        ],
        "accepted": [],
        "ledger": {},
    }
    found = sd.detect_self_review_deadlock(snap)
    assert len(found) == 1
    assert found[0]["id"] == sd.SELF_REVIEW_ID
    assert "5294" in found[0]["key"] and "5289" in found[0]["key"]


def test_self_review_healthy_when_third_seat_can_review():
    snap = {
        "live": {"flamingo-67876", "marchhare-22900", "ionos-1"},
        "idle": {"ionos-1"},
        "unaccepted": [
            _mrb(
                "https://github.com/SimonBarnett/a-search/pull/5294",
                "flamingo-67876",
                ["marchhare-22900"],
            ),
        ],
        "accepted": [],
        "ledger": {},
    }
    assert sd.detect_self_review_deadlock(snap) == []


def test_all_gave_up_fires_and_healthy_silent():
    row = _mrb(
        "https://github.com/SimonBarnett/a-search/issues/5058",
        "x",
        ["flamingo-1", "marchhare-1"],
    )
    row["task"] = "FR"
    row["url"] = "https://github.com/SimonBarnett/a-search/issues/5058"
    bad = {
        "live": {"flamingo-1", "marchhare-1"},
        "unaccepted": [row],
    }
    found = sd.detect_all_gave_up(bad)
    assert len(found) == 1
    assert found[0]["id"] == sd.ALL_GAVE_UP_ID
    healthy = {
        "live": {"flamingo-1", "marchhare-1"},
        "unaccepted": [_mrb("https://github.com/SimonBarnett/a-search/pull/1", "x")],
    }
    assert sd.detect_all_gave_up(healthy) == []


def test_all_gave_up_ignores_stall_report_rows():
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "ident": "#5181",
        "url": "https://github.com/SimonBarnett/bobiverse/issues/5181",
        "title": "Jeeves cannot ensure git webhook on SimonBarnett/a-search",
        "body": "<!-- stall-fp:stall:all-gave-up:SimonBarnett/a-search#5139 -->",
        "giveup_seats": "flamingo-48304",
    }

    assert sd.detect_all_gave_up(
        {"live": {"flamingo-48304"}, "unaccepted": [row]}
    ) == []
    ordinary_stall_title = dict(row, title="stall: a regular product issue", body="User report")
    assert len(
        sd.detect_all_gave_up(
            {"live": {"flamingo-48304"}, "unaccepted": [ordinary_stall_title]}
        )
    ) == 1


def test_sticky_auto_pin_and_healthy():
    stuck = {
        "unaccepted": [
            {
                "task": "FR",
                "repo": "SimonBarnett/a-search",
                "ident": "9999",
                "url": "https://github.com/SimonBarnett/a-search/issues/9999",
                "title": "plain search bug",
                "body": "no pin keywords here",
                "require_machine": "redqueen",
                "labels": [],
            }
        ]
    }
    found = sd.detect_sticky_auto_pin(stuck)
    assert len(found) == 1
    assert found[0]["id"] == sd.STICKY_PIN_ID
    ok = {
        "unaccepted": [
            {
                "task": "FR",
                "repo": "SimonBarnett/a-search",
                "ident": "5030",
                "url": "https://github.com/SimonBarnett/a-search/issues/5030",
                "title": "a-hasresults-monitor on redqueen",
                "body": "redeploy a-hasresults-monitor",
                "require_machine": "redqueen",
                "labels": [],
            }
        ]
    }
    assert sd.detect_sticky_auto_pin(ok) == []


def test_resync_ack_bored_healthy_and_fire():
    assert sd.detect_resync_fail({"resync_fail_streak": 2}) == []
    assert sd.detect_resync_fail({"resync_fail_streak": 3})
    now = 100_000.0
    assert sd.detect_ack_stale({"now": now, "accepted": []}) == []
    stale = sd.detect_ack_stale(
        {
            "now": now,
            "accepted": [
                {
                    "task": "FR",
                    "repo": "SimonBarnett/bobiverse",
                    "url": "https://github.com/SimonBarnett/bobiverse/issues/1",
                    "acked_at": now - sd.ACK_STALE_S - 10,
                    "accepted_by": "flamingo-1",
                }
            ],
        }
    )
    assert stale and stale[0]["id"] == sd.ACK_STALE_ID
    assert sd.detect_bored_latency({"now": now, "idle": {"flamingo-1"}, "last_bored": {}}) == []
    late = sd.detect_bored_latency(
        {
            "now": now,
            "idle": {"flamingo-1"},
            "last_bored": {"flamingo-1": now - sd.BORED_LATENCY_S - 1},
        }
    )
    assert late and late[0]["id"] == sd.BORED_LATENCY_ID


def test_filer_dedupe_comment_not_second_issue(tmp_path: Path):
    finding = {
        "id": "x",
        "key": "k",
        "fingerprint": "stall:x:k",
        "title": "stall:x:k",
        "evidence": {"a": 1},
    }
    created = []
    comments = []

    def create(title, body):
        created.append((title, body))
        return {"number": 77}

    def list_open(fp):
        return [{"number": 77, "title": fp}] if created else []

    def comment(n, body):
        comments.append((n, body))

    a1 = sf.apply_findings(
        [finding],
        home=tmp_path,
        now=1000.0,
        create=create,
        list_open=list_open,
        comment=comment,
        cooldown_s=10,
        comment_s=1,
    )
    assert any(x["action"] == "created" for x in a1)
    a2 = sf.apply_findings(
        [finding],
        home=tmp_path,
        now=1002.0,
        create=create,
        list_open=list_open,
        comment=comment,
        cooldown_s=10,
        comment_s=1,
    )
    assert any(x["action"] == "comment" for x in a2)
    assert len(created) == 1
    a3 = sf.apply_findings(
        [finding],
        home=tmp_path,
        now=1002.2,
        create=create,
        list_open=list_open,
        comment=comment,
        cooldown_s=10,
        comment_s=10,
    )
    assert any(x["action"] == "deduped" for x in a3)
    assert len(created) == 1


def test_filer_cap_and_spool(tmp_path: Path):
    def boom(title, body):
        raise RuntimeError("403")

    finding = {
        "id": "y",
        "key": "1",
        "fingerprint": "stall:y:1",
        "title": "stall:y:1",
        "evidence": {},
    }
    acts = sf.apply_findings(
        [finding],
        home=tmp_path,
        now=50.0,
        create=boom,
    )
    assert any(x["action"] == "spool" for x in acts)
    assert sf.spool_path(tmp_path).is_file()

    created = []

    def create(title, body):
        created.append(title)
        return {"number": len(created)}

    many = [
        {
            "id": "z",
            "key": str(i),
            "fingerprint": f"stall:z:{i}",
            "title": f"stall:z:{i}",
            "evidence": {},
        }
        for i in range(6)
    ]
    acts = sf.apply_findings(
        many,
        home=tmp_path / "cap",
        now=200.0,
        create=create,
        global_per_hour=2,
        cooldown_s=0,
    )
    assert len(created) == 2
    assert any(x["action"] == "capped" for x in acts)


def test_detect_all_adds_fingerprint():
    snap = {
        "live": {"a-1"},
        "idle": {"a-1"},
        "unaccepted": [],
        "resync_fail_streak": 3,
        "now": 1.0,
    }
    all_f = sd.detect_all(snap)
    assert all(x.get("fingerprint", "").startswith("stall:") for x in all_f)
