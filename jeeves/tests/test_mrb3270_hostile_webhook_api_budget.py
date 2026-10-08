"""MRB #3270 hostile pins for FR #3212 webhook-first / REST-budget contracts."""
from __future__ import annotations

import io
import urllib.error
from pathlib import Path

import chair_health as ch
import gitclaim
import github_api_budget as gab
import irc_agent

REPO = "SimonBarnett/bobiverse"


def test_mrb3270_resync_is_hourly_and_bored_budget_zero():
    assert ch.RESYNC_S >= 3600.0
    assert gab.DEFAULT_BUDGET_PER_HOUR == 1000
    assert gab.BACKOFF_FLOOR == 500
    assert gab.WEBHOOK_GAP_S == 900.0
    assert gitclaim.BORED_GITHUB_CALL_BUDGET == 0


def test_mrb3270_irc_bored_path_passes_no_live_checkers():
    """Source pin: chair !bored must not wire live GitHub checkers (FR #3212 item 3)."""
    src = Path(irc_agent.__file__).read_text(encoding="utf-8")
    assert "FR #3212: zero REST on !bored" in src
    # The offer call site must pass None for all three live checkers.
    assert "pr_exists=None" in src
    assert "is_pull=None" in src
    assert "issue_open=None" in src


def test_mrb3270_essential_uses_rate_floor_reserve(tmp_path: Path):
    logs: list[str] = []
    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=logs.append)
    bud.rate_remaining = 100
    bud.used = 50
    assert bud.allow("on-demand", essential=False) is False
    assert bud.allow("reconcile", essential=True) is True
    assert sum(1 for ln in logs if "backoff" in ln) == 1


def test_mrb3270_304_does_not_charge_budget(tmp_path: Path):
    class _Resp:
        def __init__(self):
            self.status = 304
            self.headers = {"X-RateLimit-Remaining": "4800", "ETag": '"x"'}

        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda _s: None)
    bud.set_etag("https://example.test/x", '"x"')

    def opener(req, timeout=30.0):
        return _Resp()

    out = bud.conditional_get("https://example.test/x", path="reconcile", opener=opener)
    assert out is gab.NOT_MODIFIED
    assert bud.used == 0


def test_mrb3270_failed_resync_keeps_prior_rows(tmp_path: Path):
    rows = [
        {
            "repo": REPO,
            "task": "FR",
            "id": "#99",
            "seq": 1,
            "ts": "t",
            "line": f"FR {REPO}#99",
            "url": f"https://github.com/{REPO}/issues/99",
            "title": "keep-me",
            "state": "open",
            "event": "issues",
        }
    ]
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": rows, "accepted": [], "done": [], "workers": {}},
    )

    class _Hdr(dict):
        def get(self, k, default=None):
            for key in (k, k.lower(), k.title()):
                if key in self:
                    return dict.get(self, key, default)
            return default

    def opener(req, timeout=30.0):
        raise urllib.error.HTTPError(
            req.full_url,
            403,
            "rate limit",
            _Hdr({"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "9999999999"}),
            io.BytesIO(b""),
        )

    bud = gab.GithubApiBudget(tmp_path, budget_per_hour=1000, floor=500, log=lambda _s: None)
    fetch = gab.make_budgeted_fetch(bud, token="t", path="reconcile", opener=opener)
    res = gitclaim.resync_from_github(tmp_path, [REPO], fetch_json=fetch, token="t")
    assert res["ok"]
    assert REPO in (res.get("failed") or [])
    got = gitclaim.load_unaccepted(tmp_path)
    assert len(got) == 1
    assert got[0]["id"] == "#99"


def test_mrb3270_webhook_stamp_and_gap_helper(tmp_path: Path):
    assert gab.webhook_gap_due(tmp_path, now=1_000_000.0) is False  # never stamped
    gab.stamp_git_webhook(tmp_path, now=1_000_000.0 - 60)
    assert gab.webhook_gap_due(tmp_path, now=1_000_000.0, gap_s=900) is False
    assert gab.webhook_gap_due(tmp_path, now=1_000_000.0, gap_s=30) is True
