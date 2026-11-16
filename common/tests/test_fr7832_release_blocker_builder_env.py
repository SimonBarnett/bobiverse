"""FR #7832: a seat-environment pass must not close a release-blocker."""
from __future__ import annotations

import release_blocker_close as gate


def _passes_only_with_machine_sign_in(env: dict) -> bool:
    return bool(env.get("GROK_AUTH_PATH"))


def test_fr7832_seat_pass_does_not_close_when_builder_fails():
    seat = {
        "GROK_AUTH_PATH": "EXAMPLE_MACHINE_AUTH",
        "BOB_GROK_AUTH_PATH": "EXAMPLE_BOB_AUTH",
        "PATH": "EXAMPLE_PATH",
    }
    assert _passes_only_with_machine_sign_in(seat) is True
    built = gate.run_check_in_builder_env(_passes_only_with_machine_sign_in, seat)
    assert built["passed"] is False
    assert "GROK_AUTH_PATH" not in built["env_names"]
    assert "BOB_GROK_AUTH_PATH" not in built["env_names"]
    assert "EXAMPLE_MACHINE_AUTH" not in built["summary"]
    comment = "Already green on origin/main. Covered by PR #7203."
    assert gate.may_close_release_blocker(
        comment=comment, builder_passed=built["passed"], seat_passed=True
    ) is False
    cited = (
        "builder-env pytest bob/tests/test_fr4123_startup_hold_until_turn.py "
        "ref c8a0a410 stripped GROK_AUTH_PATH BOB_GROK_AUTH_PATH"
    )
    assert gate.may_close_release_blocker(
        comment=cited, builder_passed=False, seat_passed=True
    ) is False


def test_fr7832_builder_pass_with_citation_may_close():
    comment = (
        "builder-env pytest common/tests/test_fr7832_release_blocker_builder_env.py "
        "ref f375acd8 actions not required"
    )
    assert gate.comment_cites_builder_run(comment) is True
    assert gate.may_close_release_blocker(
        comment=comment, builder_passed=True, seat_passed=False
    ) is True
    assert gate.may_close_release_blocker(
        comment="builder-env only, no sha", builder_passed=True
    ) is False
