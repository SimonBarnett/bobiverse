"""FR #139: Flush must drop forever-403 / allowlist-rejected outbox payloads."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import intake
from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"


def test_outbox_drop_reason_rejects_disallowed_and_403():
    assert intake.outbox_drop_reason({"repo": "evil/x", "title": "t"}) == "repo_not_allowed"
    assert intake.outbox_drop_reason(
        {"repo": "SimonBarnett/bobiverse", "title": "t"}, http_status=403
    ) == "repo_not_allowed"
    assert intake.outbox_drop_reason(
        {"repo": "SimonBarnett/bobiverse", "title": "t"}, error="repo_not_allowed"
    ) == "repo_not_allowed"
    assert intake.outbox_drop_reason({"repo": "evil/x", "title": "t"}) == "repo_not_allowed"
    assert intake.outbox_drop_reason({"repo": "SimonBarnett/bobiverse", "title": "t"}) is None
    assert intake.outbox_drop_reason(None) == "malformed"
    assert intake.outbox_drop_reason({"title": "t"}) == "missing_repo"


def test_flush_drops_bad_title_without_post(tmp_path: Path):
    outbox = tmp_path / "report-outbox"
    outbox.mkdir()
    stuck = {
        "kind": "issue",
        "repo": "SimonBarnett/bobiverse",
        "title": "",
        "body": "x",
        "idempotency_key": "ps-fr611-bad-title-0001",
    }
    path = outbox / "report-ps-fr611-bad-ti.json"
    path.write_text(json.dumps(stuck) + "\n", encoding="utf-8")
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            "-Flush",
            "-OutboxDir",
            str(outbox),
            "-NoDefaultOutboxes",
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(tmp_path),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DROPPED" in r.stdout
    assert "bad_title" in r.stdout
    assert not path.exists()


def test_agentic_fomprep_is_on_default_allowlist_after_pr99():
    # PR #99 is included in the combined release, so this target is now allowed.
    assert "SimonBarnett/agentic_fomprep" in intake.DEFAULT_ALLOW_REPOS


def test_flush_script_documents_drop_path():
    text = HARVEST.read_text(encoding="utf-8-sig")
    for needle in (
        "Get-IntakeAllowRepos",
        "repo_not_allowed",
        "DROPPED",
        "dropped=$dropped",
        "DEFAULT_ALLOW_REPOS",
        "Move-OutboxDropped",
    ):
        assert needle in text, needle


def test_flush_drops_disallowed_repo_without_post(tmp_path: Path):
    outbox = tmp_path / "report-outbox"
    outbox.mkdir()
    stuck = {
        "kind": "fr",
        "repo": "evil/x",
        "title": "FR: disallowed target",
        "body": "x",
        "idempotency_key": "ps-2a58ecb4dc6bdd6d2ad7a945",
    }
    path = outbox / "report-ps-2a58ecb4dc6bd.json"
    path.write_text(json.dumps(stuck) + "\n", encoding="utf-8")
    # Point every flush dir at tmp; IntakeUrl unused for allowlist drop.
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HARVEST),
            "-Flush",
            "-OutboxDir",
            str(outbox),
            "-NoDefaultOutboxes",
            "-IntakeUrl",
            "http://127.0.0.1:9/bob/v1/intake",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(tmp_path),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "DROPPED" in r.stdout
    assert "repo_not_allowed:evil/x" in r.stdout
    assert "flush: sent=0 kept=0 dropped=" in r.stdout
    assert not path.exists()
    dropped = outbox / "dropped" / path.name
    assert dropped.is_file()
    assert json.loads(dropped.read_text(encoding="utf-8"))["repo"] == "evil/x"
