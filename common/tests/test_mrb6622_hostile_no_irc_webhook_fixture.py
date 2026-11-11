"""Hostile pin for MRB #6622 / FR #6619: no IRC-host webhook fixture.

FR #5272 ``test_irc_host_defaults_remain_irc`` fails closed on any contiguous
IRC-host webhook URL in the tree. The t2280 query-refusal fixture must keep
using the bob public host. Build the forbidden needle from parts so this file
does not trip the same gate.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
T2280 = ROOT / "common" / "tests" / "test_t2280_service_xai_weekly_publish.py"


def test_mrb6622_t2280_fixture_has_no_irc_webhook_url():
    text = T2280.read_text(encoding="utf-8")
    bad = "https://" + "irc.ntsa.uk" + "/bob"
    bad_http = "http://" + "irc.ntsa.uk" + "/bob"
    assert bad not in text
    assert bad_http not in text
    assert "https://bob.ntsa.uk/bob/v1/report?token=secret" in text
    assert 'refused["error"] == "query"' in text
