"""FR #5359: Jeeves retries intake/outbox on a timer and drains more than 20."""
from __future__ import annotations

import json
from pathlib import Path

import chair_health as ch
import intake
from repo_layout import ROOT

from test_fr2595_receipt_aware_drain import _outbox_row


def test_fr5359_drain_all_more_than_20(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    for i in range(36):
        _outbox_row(
            tmp_path,
            iid=f"in_fr5359_{i:02d}",
            title=f"FR #5359 queued item {i}",
            body="queued_github_down replay",
            kind="issue",
            idem=f"idem-5359-{i}",
        )
    stats = intake.drain_intake_outbox_all(tmp_path, filer, batch=20)
    assert stats.as_counts()["filed"] == 36
    assert not list((intake.intake_root(tmp_path) / "outbox").glob("*.json"))
    assert len(filer.issues) == 36


def test_fr5359_recover_after_github_down_no_twins(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.down = True
    _outbox_row(
        tmp_path,
        iid="in_fr5359_down",
        title="FR #5359 down then up",
        body="once",
        kind="issue",
        idem="idem-5359-once",
    )
    stats = intake.drain_intake_outbox_all(tmp_path, filer, batch=20)
    assert stats.deferred == ["in_fr5359_down"]
    assert list((intake.intake_root(tmp_path) / "outbox").glob("*.json"))
    filer.down = False
    stats2 = intake.drain_intake_outbox_all(tmp_path, filer, batch=20)
    assert stats2.as_counts()["filed"] == 1
    assert not list((intake.intake_root(tmp_path) / "outbox").glob("*.json"))
    again = intake.drain_intake_outbox_all(tmp_path, filer, batch=20)
    assert again.as_counts()["filed"] == 0
    assert len(filer.issues) == 1


def test_fr5359_snapshot_and_digest(tmp_path: Path):
    _outbox_row(
        tmp_path,
        iid="in_fr5359_snap",
        title="snap",
        body="b",
        kind="issue",
        idem="idem-snap",
    )
    snap = intake.intake_outbox_snapshot(tmp_path, now=1_000_000.0)
    assert snap["count"] == 1
    assert snap["oldest_age_s"] is not None
    assert "gh_cli" in snap
    import bobreport

    doc = bobreport.build_digest_object(tmp_path, "jeeves")
    assert doc["intake_outbox"]["count"] == 1
    assert "gh_cli" in doc["intake_outbox"]


def test_fr5359_chair_jobs_retry_and_kick(tmp_path: Path):
    calls = []

    class Clock:
        def __init__(self):
            self.t = 10_000.0

        def __call__(self):
            return self.t

    clk = Clock()
    j = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=lambda s: None,
        announce=lambda s: None,
        http=lambda *a, **k: 200,
        token_loader=lambda: ("", "none"),
        clock=clk,
        sleep=lambda s: None,
        spawn=False,
    )
    j._drain_intake_outbox = lambda: calls.append("drain")
    assert j.next_intake_outbox > clk.t
    clk.t = j.next_intake_outbox + 1
    j.tick()
    assert calls == ["drain"]
    j.request_intake_outbox_drain()
    assert j.next_intake_outbox == 0.0
    j.tick()
    assert calls == ["drain", "drain"]


def test_fr5359_pins():
    irc = (ROOT / "common" / "scripts" / "chair_health.py").read_text(encoding="utf-8")
    cb = (ROOT / "common" / "scripts" / "bobcallback.py").read_text(encoding="utf-8")
    inn = (ROOT / "common" / "scripts" / "intake.py").read_text(encoding="utf-8")
    chk = (ROOT / "jeeves" / "checks" / "check_gh_cli.py").read_text(encoding="utf-8")
    assert "FR #5359" in irc and "request_intake_outbox_drain" in irc
    assert "drain_intake_outbox_all" in cb
    assert "drain_intake_outbox_all" in inn
    assert "gh_cli_missing" in chk
    assert not (ROOT / "common" / "scripts" / "intake.py").read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr5359_gh_check_plugin():
    import jeeves_checks

    plugs = jeeves_checks.load_plugin_checks()
    assert "gh_cli" in plugs
    detail, findings, errors = plugs["gh_cli"]["run"](Path("."), Path("."))
    assert "gh_cli" in detail
    if detail.get("ok"):
        assert errors == []
    else:
        assert any("gh_cli_missing" in e for e in errors)
