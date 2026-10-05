"""FR #2595: receipt-aware safe drain for harvest intake outbox."""
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


def test_fr2595_helpers_detect_receipt_and_probe():
    assert intake.is_harvest_worker_receipt(
        kind="harvest",
        title="harvest: DONE MRB #2594 FAIL",
        body="Session summary:\nDONE MRB #2594 FAIL",
    )
    assert not intake.is_harvest_worker_receipt(
        kind="harvest",
        title="harvest: durable tip utf8 write playbook",
        body="Session summary:\nWrite tip scripts with python bytes.",
    )
    assert intake.is_do_not_file_probe(
        title="fr1993-redeploy-probe-do-not-file",
        body="probe",
    )
    assert intake.is_do_not_file_probe(
        title="fr1993-redeploy-b-probe-do-not-file",
        body="",
    )


def test_fr2595_file_submission_records_receipt_without_pr(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/bobiverse",
            "title": "harvest: DONE MRB #2594 FAIL receipt",
            "body": "Session summary:\nDONE MRB SimonBarnett/bobiverse#2594 FAIL",
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_receipt2595")
    assert rec["state"] == "receipt_recorded"
    assert rec.get("url") in (None, "")
    assert filer.prs == []
    assert filer.issues == []


def test_fr2595_file_submission_drops_probe(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/bobiverse",
            "title": "fr1993-redeploy-probe-do-not-file",
            "body": "probe-shape-only-do-not-file",
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_probe2595")
    assert rec["state"] == "dropped_probe"
    assert filer.prs == []


def test_fr2595_drain_dry_run_counts_without_mutating(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    p1 = _outbox_row(
        tmp_path,
        iid="in_done1",
        title="harvest: DONE FR #1",
        body="Session summary:\nDONE FR #1",
    )
    p2 = _outbox_row(
        tmp_path,
        iid="in_probe1",
        title="fr1993-redeploy-probe-do-not-file",
        body="do-not-file",
    )
    p3 = _outbox_row(
        tmp_path,
        iid="in_real1",
        title="harvest: durable playbook for tip utf8",
        body="Session summary:\nAlways write tip scripts with python/git bytes.",
    )
    stats = intake.drain_intake_outbox(tmp_path, filer, limit=20, dry_run=True)
    assert stats.dry_run is True
    assert "in_done1" in stats.recorded_receipt
    assert "in_probe1" in stats.dropped_probe
    assert "in_real1" in stats.filed
    assert p1.is_file() and p2.is_file() and p3.is_file()
    assert filer.prs == []


def test_fr2595_drain_applies_receipt_rules_and_dedupe(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    _outbox_row(
        tmp_path,
        iid="in_done2",
        title="harvest: twin DONE of #2594",
        body="Session summary:\ntwin DONE MRB #2594",
        idem="receipt-key-2595",
    )
    # Pre-seed idempotent record so duplicate row is skipped.
    intake._save_record(
        tmp_path,
        {
            "intake_id": "in_prior",
            "kind": "harvest",
            "repo": "SimonBarnett/bobiverse",
            "title": "prior",
            "idempotency_key": "same-key-2595",
            "state": "receipt_recorded",
            "url": None,
            "queued": False,
        },
    )
    _outbox_row(
        tmp_path,
        iid="in_dup",
        title="harvest: twin DONE of #2594 again",
        body="Session summary:\nduplicate DONE",
        idem="same-key-2595",
    )
    # Existing intake/<iid> PR on filer (branch match).
    filer.prs.append(
        {
            "repo": "SimonBarnett/bobiverse",
            "number": 9001,
            "title": "existing",
            "body": "",
            "branch": "intake/in_existing",
            "files": [],
            "labels": [],
            "draft": True,
            "url": "https://github.com/SimonBarnett/bobiverse/pull/9001",
        }
    )
    _outbox_row(
        tmp_path,
        iid="in_existing",
        title="harvest: durable lesson already branched",
        body="Session summary:\nA real playbook already has intake/in_existing.",
        idem="other-key",
    )
    _outbox_row(
        tmp_path,
        iid="in_probe2",
        title="fr1993-redeploy-b-probe-do-not-file",
        body="do-not-file",
        idem="probe-key",
    )
    _outbox_row(
        tmp_path,
        iid="in_real2",
        title="harvest: durable tip utf8 write",
        body="Session summary:\nWrite tip scripts with python/git bytes; never UTF-16 redirect.",
        idem="real-key",
    )

    stats = intake.drain_intake_outbox(tmp_path, filer, limit=20, dry_run=False)
    assert "in_dup" in stats.skipped_duplicate
    assert "in_existing" in stats.skipped_duplicate
    assert "in_probe2" in stats.dropped_probe
    assert "in_real2" in stats.filed
    assert "in_done2" in stats.recorded_receipt
    assert not (intake.intake_root(tmp_path) / "outbox" / "in_probe2.json").exists()
    assert not (intake.intake_root(tmp_path) / "outbox" / "in_real2.json").exists()
    # Only the real playbook creates a new PR (existing stub PR already in filer.prs).
    new_prs = [p for p in filer.prs if p["number"] != 9001]
    assert len(new_prs) == 1
    assert new_prs[0]["branch"] == "intake/in_real2"


def test_fr2595_drain_pending_uses_receipt_aware_drain():
    import bobcallback

    text = Path(bobcallback.__file__).read_text(encoding="utf-8-sig")
    assert "drain_intake_outbox" in text
    # Must pass through (no bypass that calls file_submission directly for outbox).
    assert "intake.drain_intake_outbox" in text
