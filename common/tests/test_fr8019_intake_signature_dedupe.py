"""FR #8019: explicit per-job dedupe_key still falls back to title+signature."""
from __future__ import annotations

from pathlib import Path

import intake


REPO = "SimonBarnett/bobiverse"
TITLE = "bug: OpenCode hard-ceiling kill"


def _process(home: Path, payload: dict, filer: intake.FakeGitHubFiler) -> intake.IntakeResult:
    return intake.process_intake(
        home,
        payload,
        filer=filer,
        rate=intake.RateLimiter(per_min=60),
        client_ip="127.0.0.1",
    )


def _ceiling_body(*, seat: str, job: str, elapsed: int, intake_id: str = "") -> str:
    extra = f"intake id={intake_id}\n" if intake_id else ""
    return (
        "what: opencode watchdog killed a turn at the hard ceiling\n"
        "machine: redqueen\n"
        f"seat: {seat}\n"
        f"job: {job}\n"
        f"elapsed_ms: {elapsed}\n"
        "reason: hard ceiling 1800000ms\n"
        f"{extra}"
    )


def test_fr8019_normalize_strips_job_seat_elapsed():
    a = intake.normalize_message_for_dedupe(
        TITLE,
        _ceiling_body(seat="redqueen-1001", job="FR SimonBarnett/bobiverse#7793", elapsed=1800000),
    )
    b = intake.normalize_message_for_dedupe(
        TITLE,
        _ceiling_body(
            seat="redqueen-2002",
            job="FR SimonBarnett/bobiverse#8009",
            elapsed=1799000,
            intake_id="in_abcdef0123456789",
        ),
    )
    assert a == b
    assert "7793" not in a and "8009" not in a
    assert "1001" not in a and "2002" not in a
    assert "hard ceiling 1800000ms" in a
    assert "opencode watchdog killed a turn at the hard ceiling" in a


def test_fr8019_per_job_keys_comment_on_open_same_signature(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    r1 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": TITLE,
            "body": _ceiling_body(
                seat="redqueen-14160",
                job="FR SimonBarnett/bobiverse#7793",
                elapsed=1800000,
            ),
            "idempotency_key": "fr8019-a",
            "dedupe_key": "oc-ceiling|redqueen|redqueen-14160|FR SimonBarnett/bobiverse#7793|hard-ceiling",
        },
        filer,
    )
    assert r1.body.get("action") == "filed"
    n = r1.body["number"]
    assert len(filer.issues) == 1

    r2 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": TITLE,
            "body": _ceiling_body(
                seat="redqueen-17556",
                job="FIX SimonBarnett/bobiverse#8004",
                elapsed=1795000,
            ),
            "idempotency_key": "fr8019-b",
            "dedupe_key": "oc-ceiling|redqueen|redqueen-17556|FIX SimonBarnett/bobiverse#8004|hard-ceiling",
        },
        filer,
    )
    assert r2.body.get("action") == "commented"
    assert r2.body.get("number") == n
    assert len(filer.issues) == 1
    assert len(filer.comments) == 1
    assert "redqueen-17556" in filer.comments[0]["body"]
    assert "FIX SimonBarnett/bobiverse#8004" in filer.comments[0]["body"]


def test_fr8019_different_signature_still_files(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    r1 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": TITLE,
            "body": _ceiling_body(
                seat="redqueen-1",
                job="FR SimonBarnett/bobiverse#1",
                elapsed=1800000,
            ),
            "idempotency_key": "fr8019-d1",
            "dedupe_key": "oc-ceiling|a|1|hard-ceiling",
        },
        filer,
    )
    r2 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": TITLE,
            "body": (
                "what: opencode watchdog killed a turn for a different reason\n"
                "machine: redqueen\n"
                "seat: redqueen-2\n"
                "job: FR SimonBarnett/bobiverse#2\n"
                "elapsed_ms: 100\n"
                "reason: soft limit\n"
            ),
            "idempotency_key": "fr8019-d2",
            "dedupe_key": "oc-ceiling|b|2|soft-limit",
        },
        filer,
    )
    assert r1.body.get("action") == "filed"
    assert r2.body.get("action") == "filed"
    assert r1.body.get("number") != r2.body.get("number")
    assert len(filer.issues) == 2


def test_fr8019_exact_dedupe_key_still_first(tmp_path: Path):
    """Same caller key still comments even when titles differ (#4963 path)."""
    filer = intake.FakeGitHubFiler()
    r1 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": "alpha",
            "body": "body-a",
            "idempotency_key": "fr8019-e1",
            "dedupe_key": "stable|shared|key",
        },
        filer,
    )
    r2 = _process(
        tmp_path,
        {
            "kind": "issue",
            "repo": REPO,
            "title": "beta different",
            "body": "body-b totally different",
            "idempotency_key": "fr8019-e2",
            "dedupe_key": "stable|shared|key",
        },
        filer,
    )
    assert r1.body.get("action") == "filed"
    assert r2.body.get("action") == "commented"
    assert r2.body.get("number") == r1.body["number"]
