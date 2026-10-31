"""FR #5359: startup health names a missing GitHub CLI."""

from __future__ import annotations

CHECK_NAME = "gh_cli"
INCLUDE_IN_DEFAULT = True


def run(home, chair_home):
    import intake

    _ = home, chair_home
    ok = bool(intake.gh_cli_available())
    detail = {"ok": ok, "gh_cli": ok, "fr": 5359}
    if ok:
        return detail, [], []
    return detail, [], ["gh_cli_missing: install GitHub CLI (gh); intake outbox will queue"]
