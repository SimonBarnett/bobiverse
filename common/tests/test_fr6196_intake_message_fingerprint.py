"""FR #6196: intake derives message fingerprint when dedupe_key is absent."""
from __future__ import annotations

from pathlib import Path

import intake


REPO = "SimonBarnett/bobiverse"


def _process(home: Path, payload: dict, filer: intake.FakeGitHubFiler) -> intake.IntakeResult:
    return intake.process_intake(
        home,
        payload,
        filer=filer,
        rate=intake.RateLimiter(per_min=60),
        client_ip="127.0.0.1",
    )


def test_fr6196_normalize_strips_pid_timestamp_intake_id_keeps_error():
    a = intake.normalize_message_for_dedupe(
        "stall:bored-latency:redqueen-14160",
        "lag_s: 977\nts=2026-11-07T15:44:37Z\nintake id=in_74124dac0fa443bb\nError: timeout",
    )
    b = intake.normalize_message_for_dedupe(
        "stall:bored-latency:redqueen-17556",
        "lag_s: 636\nts=2026-11-07T15:47:40Z\nintake id=in_488a457ec4ec4ec6\nError: timeout",
    )
    assert a == b
    assert "14160" not in a and "17556" not in a
    assert "timeout" in a
    assert "stall:bored-latency:redqueen" in a


def test_fr6196_normalize_keeps_distinct_errors_separate():
    a = intake.normalize_message_for_dedupe(
        "import failure", "Error E_MERGE at tools/dbimport.py:40"
    )
    b = intake.normalize_message_for_dedupe(
        "import failure", "Error E_PARSE at tools/dbimport.py:40"
    )
    assert a != b


def test_fr6196_no_dedupe_key_same_message_comments(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    p1 = {
        "kind": "issue",
        "repo": REPO,
        "title": "stall:bored-latency:redqueen-14160",
        "body": "lag_s: 977\nError: chair stall scan",
        "idempotency_key": "fr6196-a",
    }
    p2 = {
        "kind": "issue",
        "repo": REPO,
        "title": "stall:bored-latency:redqueen-17556",
        "body": "lag_s: 636\nError: chair stall scan",
        "idempotency_key": "fr6196-b",
    }
    r1 = _process(tmp_path, p1, filer)
    assert r1.body.get("action") == "filed"
    n = r1.body["number"]
    assert len(filer.issues) == 1
    body0 = filer.issues[0].get("body") or ""
    assert "intake-dedupe:" in body0
    rec = intake.load_record(tmp_path, r1.body["intake_id"])
    assert str(rec.get("dedupe_key") or "").startswith("msgfp:")

    r2 = _process(tmp_path, p2, filer)
    assert r2.body.get("action") == "commented"
    assert r2.body.get("number") == n
    assert len(filer.issues) == 1
    assert len(filer.comments) == 1
    # raw original preserved on the comment
    assert "redqueen-17556" in filer.comments[0]["body"]
    assert "lag_s: 636" in filer.comments[0]["body"]


def test_fr6196_different_errors_file_separate(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    r1 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": "crash: ImportError",
            "body": "ImportError: missing foo",
            "idempotency_key": "fr6196-d1",
        },
        filer,
    )
    r2 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": "crash: ValueError",
            "body": "ValueError: bad bar",
            "idempotency_key": "fr6196-d2",
        },
        filer,
    )
    assert r1.body.get("action") == "filed"
    assert r2.body.get("action") == "filed"
    assert r1.body.get("number") != r2.body.get("number")
    assert len(filer.issues) == 2


def test_fr6196_explicit_dedupe_key_unchanged(tmp_path: Path):
    """Caller dedupe_key still wins; msgfp not used when key present."""
    filer = intake.FakeGitHubFiler()
    r1 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": "alpha title",
            "body": "alpha body",
            "idempotency_key": "fr6196-e1",
            "dedupe_key": "stable|caller|key",
        },
        filer,
    )
    r2 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": "totally different title",
            "body": "totally different body",
            "idempotency_key": "fr6196-e2",
            "dedupe_key": "stable|caller|key",
        },
        filer,
    )
    assert r1.body.get("action") == "filed"
    assert r2.body.get("action") == "commented"
    assert r2.body.get("number") == r1.body["number"]
    marker = intake.intake_dedupe_marker(REPO, "stable|caller|key")
    assert marker in (filer.issues[0].get("body") or "")


def test_fr6196_closed_match_reopens(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    r1 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": "stall:bored-latency:redqueen-14160",
            "body": "Error: chair stall scan",
            "idempotency_key": "fr6196-c1",
        },
        filer,
    )
    filer.issues[0]["state"] = "closed"
    r2 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": "stall:bored-latency:redqueen-17556",
            "body": "Error: chair stall scan",
            "idempotency_key": "fr6196-c2",
        },
        filer,
    )
    assert r2.body.get("action") == "reopened"
    assert r2.body.get("number") == r1.body["number"]
    assert filer.issues[0]["state"] == "open"


def test_fr6196_derive_key_stable_and_capped():
    k = intake.derive_message_dedupe_key("t", "b")
    assert k.startswith("msgfp:")
    assert len(k) <= 128
    assert k == intake.derive_message_dedupe_key("t", "b")

def test_fr6196_hyphenated_machine_pid_still_dedupes():
    """Trailing -<digits> strip must leave hyphenated machine ids intact (MRB #6199)."""
    a = intake.normalize_message_for_dedupe(
        "stall:bored-latency:ce-priority-dev1-12345",
        "Error: timeout",
    )
    b = intake.normalize_message_for_dedupe(
        "stall:bored-latency:ce-priority-dev1-99999",
        "Error: timeout",
    )
    assert a == b
    assert "12345" not in a and "99999" not in a
    assert "ce-priority-dev1" in a