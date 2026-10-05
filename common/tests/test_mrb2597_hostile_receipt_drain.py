"""MRB #2597 hostile tests for receipt-aware intake drain (FR #2595)."""
from __future__ import annotations

import json
from pathlib import Path

import intake


def _outbox_row(
    home: Path,
    *,
    iid: str,
    title: str,
    body: str,
    kind: str = "harvest",
    idem: str = "",
) -> Path:
    root = intake.intake_root(home)
    norm = {
        "kind": kind,
        "repo": "SimonBarnett/bobiverse",
        "title": title,
        "body": body,
        "files": [],
        "source": {"machine": "ionos", "agent": "test", "skill_book": "harvest", "version": "-"},
        "contact": "",
        "contact_public": False,
        "idempotency_key": idem or f"idem-{iid}",
        "keyed": True,
    }
    path = root / "outbox" / f"{iid}.json"
    path.write_text(
        json.dumps({"norm": norm, "intake_id": iid, "quarantine": False}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def test_mrb2597_playbook_citing_fr_number_still_files_pr(tmp_path: Path):
    """Bare FR #N / 'merged' in a real playbook must not become receipt_recorded."""
    assert not intake.is_harvest_worker_receipt(
        kind="harvest",
        title="harvest: tip utf8 write playbook",
        body="Session summary:\nLesson for FR #890 Clear-BobiverseSeatDisk.",
    )
    assert not intake.is_harvest_worker_receipt(
        kind="harvest",
        title="harvest: after merge restart ircBob",
        body="Session summary:\nAfter merged tip, restart only ircBob.",
    )
    filer = intake.FakeGitHubFiler()
    _outbox_row(
        tmp_path,
        iid="in_play_fr",
        title="harvest: tip utf8 write playbook",
        body="Session summary:\nLesson for FR #890 seat disk reclaim.",
    )
    stats = intake.drain_intake_outbox(tmp_path, filer, limit=20, dry_run=False)
    assert "in_play_fr" in stats.filed
    assert "in_play_fr" not in stats.recorded_receipt
    assert len(filer.prs) == 1


def test_mrb2597_strong_receipt_markers_still_record_only(tmp_path: Path):
    assert intake.is_harvest_worker_receipt(
        kind="harvest",
        title="harvest: DONE MRB #2594 FAIL",
        body="Session summary:\nDONE MRB SimonBarnett/bobiverse#2594 FAIL",
    )
    assert intake.is_harvest_worker_receipt(
        kind="harvest",
        title="harvest: twin of #2594",
        body="Session summary:\ntwin duplicate of #2594",
    )
    filer = intake.FakeGitHubFiler()
    _outbox_row(
        tmp_path,
        iid="in_done_mrb",
        title="harvest: GIVEUP FR #1 blocked",
        body="Session summary:\nGIVEUP FR SimonBarnett/bobiverse#1",
    )
    stats = intake.drain_intake_outbox(tmp_path, filer, limit=20, dry_run=False)
    assert "in_done_mrb" in stats.recorded_receipt
    assert filer.prs == []


def test_mrb2597_fr1812_existing_pr_url_wins_over_receipt(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/bobiverse",
            "title": "harvest: DONE FR #2595 PR opened",
            "body": (
                "Session summary:\nDONE FR SimonBarnett/bobiverse#2595\n"
                "https://github.com/SimonBarnett/bobiverse/pull/2597"
            ),
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_link1812")
    assert rec["state"] == "linked_existing_pr"
    assert rec["number"] == 2597
    assert filer.prs == []


def test_mrb2597_drain_returns_drain_result_not_list(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    stats = intake.drain_intake_outbox(tmp_path, filer, limit=5, dry_run=True)
    assert isinstance(stats, intake.DrainResult)
    assert not isinstance(stats, list)
    counts = stats.as_counts()
    assert counts["dry_run"] is True
    assert "filed" in counts and "recorded_receipt" in counts


def test_mrb2597_bobcallback_logs_receipt_aware_counts():
    import bobcallback

    text = Path(bobcallback.__file__).read_text(encoding="utf-8-sig")
    assert "intake.drain_intake_outbox" in text
    assert "as_counts" in text
    assert "intake_outbox_drain" in text


def test_mrb2597_webhooks_doc_mentions_receipt_aware_drain():
    doc = Path(__file__).resolve().parents[2] / "jeeves" / "docs" / "webhooks.md"
    text = doc.read_text(encoding="utf-8")
    assert "FR #2595" in text
    assert "receipt-aware" in text
    assert "Drain-BobiverseIntakeOutbox.ps1" in text
