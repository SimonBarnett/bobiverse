"""FR #6348: full !assign refusal stdout line + outcome tokens."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gitclaim  # noqa: E402


def test_fr6348_long_reason_not_truncated():
    long = "x" * 350
    line = gitclaim.format_assign_refusal_log(
        nick="simon",
        worker="flamingo-50408",
        repo="SimonBarnett/bobiverse",
        ident="#6346",
        task="FR",
        reason=f"detail {long}",
        redact_fn=lambda s: s,
    )
    assert len(line) > 300
    assert long in line
    assert line.startswith("INFO git-assign refused outcome=")
    assert "\n" not in line


def test_fr6348_newline_reason_is_one_line():
    reason = "first line\nsecond line\r\nthird"
    line = gitclaim.format_assign_refusal_log(
        nick="simon",
        worker="flamingo-1",
        repo="SimonBarnett/bobiverse",
        ident="99",
        task="mrb",
        reason=reason,
        redact_fn=lambda s: s,
    )
    assert "\n" not in line
    assert "\r" not in line
    assert "first line second line third" in line
    assert line.startswith("INFO git-assign refused ")


def test_fr6348_outcome_tokens():
    cases = [
        ("accepted_by_seat", "SimonBarnett/bobiverse#1 FR: accepted by live seat flamingo-9"),
        (
            "not_queued_skipped",
            "SimonBarnett/bobiverse#2 FR: not in the unaccepted queue (skipped FR skill)",
        ),
        ("superseded_by_pr", "FR superseded by an open PR"),
        ("busy", "flamingo-50408: busy (FR SimonBarnett/bobiverse#10)"),
        ("cooldown", "row is on GIVEUP/NACK cooldown"),
    ]
    for token, reason in cases:
        line = gitclaim.format_assign_refusal_log(
            nick="simon",
            worker="flamingo-50408",
            repo="SimonBarnett/bobiverse",
            ident="#1",
            task="FR",
            reason=reason,
            redact_fn=lambda s: s,
        )
        assert f"outcome={token}" in line, (token, line)


def test_fr6348_redacts_reason():
    secret = "Bearer " + ("a" * 40)
    line = gitclaim.format_assign_refusal_log(
        nick="simon",
        worker="flamingo-1",
        repo="SimonBarnett/bobiverse",
        ident="#1",
        task="FR",
        reason=f"leak {secret}",
    )
    assert secret not in line
    assert "redacted" in line.lower()
