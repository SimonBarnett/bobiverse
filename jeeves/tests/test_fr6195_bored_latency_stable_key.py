"""FR #6190 / #6195: bored-latency stall key is stable machine id, not ephemeral nick PID."""
from __future__ import annotations

from pathlib import Path

import stall_detectors as sd
import stall_filer as sf


def test_fr6195_bored_latency_key_is_machine_not_pid():
    now = 1_000_000.0
    lag = sd.BORED_LATENCY_S + 10
    snap = {
        "now": now,
        "idle": {"redqueen-14160", "redqueen-17556"},
        "last_bored": {
            "redqueen-14160": now - lag,
            "redqueen-17556": now - lag - 5,
        },
    }
    found = sd.detect_bored_latency(snap)
    assert len(found) == 1
    f = found[0]
    assert f["key"] == "redqueen"
    assert f["id"] == sd.BORED_LATENCY_ID
    assert f["evidence"]["machine"] == "redqueen"
    assert f["evidence"]["nick"].startswith("redqueen-")
    assert "lag_s" in f["evidence"]
    assert f["title"] == "stall:bored-latency:redqueen"
    # fingerprint is attached by detect_all
    assert sd.fingerprint(f["id"], f["key"]) == "stall:bored-latency:redqueen"


def test_fr6195_two_machines_remain_distinct():
    now = 1_000_000.0
    lag = sd.BORED_LATENCY_S + 1
    snap = {
        "now": now,
        "idle": {"redqueen-1", "flamingo-2"},
        "last_bored": {
            "redqueen-1": now - lag,
            "flamingo-2": now - lag,
        },
    }
    found = sd.detect_bored_latency(snap)
    assert {f["key"] for f in found} == {"redqueen", "flamingo"}
    assert {sd.fingerprint(f["id"], f["key"]) for f in found} == {
        "stall:bored-latency:redqueen",
        "stall:bored-latency:flamingo",
    }


def test_fr6195_filer_second_pid_comments_same_issue(tmp_path: Path):
    """Same machine, different nick PIDs -> one create then comment (stable fp)."""
    now = 1_000_000.0
    lag = sd.BORED_LATENCY_S + 20
    f1 = sd.detect_all(
        {
            "now": now,
            "idle": {"redqueen-14160"},
            "last_bored": {"redqueen-14160": now - lag},
            "unaccepted": [],
            "accepted": [],
            "live": {"redqueen-14160"},
        }
    )
    f2 = sd.detect_all(
        {
            "now": now + 60,
            "idle": {"redqueen-17556"},
            "last_bored": {"redqueen-17556": now + 60 - lag},
            "unaccepted": [],
            "accepted": [],
            "live": {"redqueen-17556"},
        }
    )
    bored1 = [x for x in f1 if x["id"] == sd.BORED_LATENCY_ID]
    bored2 = [x for x in f2 if x["id"] == sd.BORED_LATENCY_ID]
    assert len(bored1) == 1 and len(bored2) == 1
    assert bored1[0]["fingerprint"] == bored2[0]["fingerprint"] == "stall:bored-latency:redqueen"

    created = []
    comments = []

    def create(title, body):
        created.append((title, body))
        assert "machine=`redqueen`" in body or '"machine": "redqueen"' in body or "machine=`redqueen`" in body.replace(" ", "")
        assert "redqueen-14160" in body
        return {"number": 6190}

    def list_open(fp):
        return [{"number": 6190, "title": fp}] if created else []

    def comment(n, body):
        comments.append((n, body))
        assert "redqueen-17556" in body

    a1 = sf.apply_findings(
        bored1,
        home=tmp_path,
        now=now,
        create=create,
        list_open=list_open,
        comment=comment,
        cooldown_s=10,
        comment_s=1,
    )
    assert any(x["action"] == "created" for x in a1)
    a2 = sf.apply_findings(
        bored2,
        home=tmp_path,
        now=now + 60,
        create=create,
        list_open=list_open,
        comment=comment,
        cooldown_s=10,
        comment_s=1,
    )
    assert any(x["action"] == "comment" for x in a2)
    assert len(created) == 1
    assert len(comments) == 1
    body0 = created[0][1]
    assert "machine=`redqueen`" in body0 or "key=`redqueen`" in body0


def test_fr6195_issue_body_names_stable_machine_and_volatile_nick():
    finding = {
        "id": sd.BORED_LATENCY_ID,
        "key": "redqueen",
        "fingerprint": "stall:bored-latency:redqueen",
        "title": "stall:bored-latency:redqueen",
        "evidence": {"nick": "redqueen-14160", "machine": "redqueen", "lag_s": 977},
    }
    body = sf.issue_body(finding, excerpt="chair stall scan")
    assert "fingerprint=`stall:bored-latency:redqueen`" in body
    assert "key=`redqueen`" in body
    assert "redqueen-14160" in body
    assert "machine=`redqueen`" in body or '"machine": "redqueen"' in body


def test_fr6195_hyphenated_machine_fallback_strips_trailing_pid():
    """Fallback regex must keep hyphenated machine ids (CodeRabbit / MRB #6197)."""
    assert sd._bored_latency_stable_key("ce-priority-dev1-12345") == "ce-priority-dev1"
    assert sd._bored_latency_stable_key("redqueen-14160") == "redqueen"
    assert sd._bored_latency_stable_key("unparsable") == "unparsable"


def test_fr6195_issue_body_machine_only_from_evidence():
    """Do not present a non-machine finding key as machine= (MRB #6197)."""
    finding = {
        "id": "ack-stale",
        "key": "row-xyz",
        "fingerprint": "stall:ack-stale:row-xyz",
        "title": "stall:ack-stale:row-xyz",
        "evidence": {"nick": "redqueen-1", "lag_s": 10},
    }
    body = sf.issue_body(finding)
    assert "machine=`row-xyz`" not in body
    assert "nick=`redqueen-1`" in body