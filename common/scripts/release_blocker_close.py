"""FR #7832: a release-blocker closes only after a builder-environment pass.

The release builder has no machine Grok sign-in. A seat that is signed in
must not close the issue from that seat run alone.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

# Names only. Never log or comment the values.
STRIP_FOR_BUILDER = ("GROK_AUTH_PATH", "BOB_GROK_AUTH_PATH")
_SHA = re.compile(r"\b[0-9a-fA-F]{7,40}\b")


def builder_pytest_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy *base* with machine Grok auth env removed and the builder marker set."""
    env = {str(k): str(v) for k, v in dict(base or {}).items()}
    for name in STRIP_FOR_BUILDER:
        env.pop(name, None)
    env["BOB_BUILDER_ENV"] = "1"
    return env


def builder_env_summary() -> str:
    """Names only. Safe to paste into a close comment."""
    stripped = ", ".join(STRIP_FOR_BUILDER)
    return f"builder-env stripped {stripped}; set BOB_BUILDER_ENV"


def comment_cites_builder_run(comment: str) -> bool:
    """True when the close comment names a builder run, a command or CI link, and a SHA."""
    text = comment or ""
    low = text.lower()
    has_marker = "builder-env" in low
    has_sha = _SHA.search(text) is not None
    has_ref = ("pytest" in low) or ("/actions/runs/" in low)
    return has_marker and has_sha and has_ref


def may_close_release_blocker(
    *,
    comment: str,
    builder_passed: bool,
    seat_passed: bool = False,
) -> bool:
    """Seat-only green is not enough. Builder pass plus a cited run is required.

    *seat_passed* is recorded so callers cannot treat it as the close signal.
    """
    del seat_passed
    if not builder_passed:
        return False
    return comment_cites_builder_run(comment)


def run_check_in_builder_env(check, seat_env: Mapping[str, str] | None = None) -> dict:
    """Run *check(env)* with auth env stripped. A raised check is a failed builder run."""
    env = builder_pytest_env(seat_env)
    try:
        passed = bool(check(env))
    except Exception:
        passed = False
    return {
        "passed": passed,
        "builder_env": True,
        "summary": builder_env_summary(),
        "env_names": sorted(env),
    }
