"""MRB #5419 hostile pins for FR #5359 intake/outbox retry (docs/mrb-5419)."""
from __future__ import annotations

from pathlib import Path

import chair_health as ch
import intake
from repo_layout import ROOT
from test_fr2595_receipt_aware_drain import _outbox_row


def test_mrb5419_resync_ok_kicks_intake_drain():
    t = (ROOT / "common" / "scripts" / "chair_health.py").read_text(encoding="utf-8")
    i = t.index("if res.get(\"ok\"):")
    chunk = t[i : i + 400]
    assert "request_intake_outbox_drain" in chunk
    assert "budget-backoff" in chunk


def test_mrb5419_gh_missing_backoff_and_announce(tmp_path: Path, monkeypatch):
    notes = []
    clk = {"t": 20_000.0}

    class Clock:
        def __call__(self):
            return clk["t"]

    j = ch.ChairJobs(
        tmp_path,
        tmp_path,
        log=lambda s: notes.append(s),
        announce=lambda s: notes.append("ANN " + s),
        http=lambda *a, **k: 200,
        token_loader=lambda: ("", "none"),
        clock=Clock(),
        sleep=lambda s: None,
        spawn=False,
    )
    _outbox_row(
        tmp_path,
        iid="in_mrb5419",
        title="queued",
        body="b",
        kind="issue",
        idem="idem-mrb5419",
    )
    monkeypatch.setattr(intake, "gh_cli_available", lambda: False)
    before = j._intake_backoff_s
    j._drain_intake_outbox()
    assert j._intake_backoff_s == min(ch.INTAKE_OUTBOX_BACKOFF_MAX_S, before * 2.0)
    assert any("INTAKE OUTBOX" in n and "MISSING" in n for n in notes)


def test_mrb5419_drain_all_stops_when_only_deferred(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.down = True
    for i in range(5):
        _outbox_row(
            tmp_path,
            iid=f"in_mrb5419_d{i}",
            title=f"down {i}",
            body="queued_github_down",
            kind="issue",
            idem=f"idem-mrb5419-d{i}",
        )
    calls = {"n": 0}
    real = intake.drain_intake_outbox

    def wrapped(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    intake.drain_intake_outbox = wrapped  # type: ignore[method-assign]
    try:
        stats = intake.drain_intake_outbox_all(tmp_path, filer, batch=20, max_batches=8)
    finally:
        intake.drain_intake_outbox = real  # type: ignore[method-assign]
    assert stats.deferred
    assert calls["n"] == 1


def test_mrb5419_webhooks_doc_names_timer():
    doc = (ROOT / "jeeves" / "docs" / "webhooks.md").read_text(encoding="utf-8")
    assert "FR #5359" in doc
    assert "drain_intake_outbox_all" in doc
    assert "check_gh_cli" in doc
    assert not (ROOT / "jeeves" / "docs" / "webhooks.md").read_bytes().startswith(b"\xef\xbb\xbf")
