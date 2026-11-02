"""FR #6012: injected priority_runner must still run for valid PRIORITY status."""
from __future__ import annotations

import airc_console as ac
import airc_priority as ap
from airc_auth_helpers import ops_auth


def test_fr6012_injected_runner_used_without_live_allowlist():
    seen: list = []

    def runner(subcmd, instance_id, **kwargs):
        jid = kwargs.get("job_id") or "11000001"
        seen.append((subcmd, instance_id, jid))
        return ap.PriorityVerbResult(
            ok=True,
            exit_code=0,
            job_id=jid,
            payload={"ok": True},
        )

    auth = ops_auth("bob-marchhare", channel="#marchhare")
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=auth,
        nick="marchhare_console",
        priority_runner=runner,
    )
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console "
        ":id=11000001 PRIORITY status"
    )
    assert hr is not None
    assert hr.action == "priority"
    assert "code=bad_id" not in (hr.reply or "")
    assert "priority_not_installed" not in (hr.reply or "")
    assert seen and seen[0][0] == "status" and seen[0][2] == "11000001"
