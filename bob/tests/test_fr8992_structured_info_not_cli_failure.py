"""FR #8992: exit 0xffffffff plus Grok JSON info/debug is an external kill."""
from __future__ import annotations

import bob_worker as bw

BILLING = (
    'r": "1.0.92", "lvl": "info", "msg": "billing: fetched credits config", '
    '"ctx": {"config": {"creditUsagePercent": 100.0, "prepaidBalance": {"val": 0}, '
    '"subscriptionTiers": "SuperGrok"}}\n'
)


def test_fr8992_billing_info_is_external_kill():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        job_key="",
        machine="redqueen",
        nick="redqueen-6520",
        kind="grok",
        agent_pid=1368,
        stderr_tail=BILLING,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert len(posts) == 1
    body = posts[0]["body"]
    assert "end=external-kill" in body
    assert "end=cli-failure" not in body
    assert posts[0]["title"].startswith("bug: seat ended")
    assert "FR #8992" in body


def test_fr8992_info_error_level_stays_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=4294967295,
        machine="redqueen",
        kind="grok",
        stderr_tail='{"lvl": "error", "msg": "billing: fetched credits config"}\n',
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "end=cli-failure" in posts[0]["body"]


def test_fr8992_exit_one_info_stays_cli_failure():
    posts = []
    bw.report_agent_cli_nonzero_exit(
        exit_code=1,
        machine="redqueen",
        kind="grok",
        stderr_tail=BILLING,
        filer_post=lambda p: posts.append(p) or {"ok": True},
    )
    assert "end=cli-failure" in posts[0]["body"]
