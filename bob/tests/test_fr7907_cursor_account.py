"""FR #7907: Cursor CLI account on the digest and tray pool row.

Email or literal none only. Serialized payloads must not carry token fields.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import bobreport

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")

TOKEN = "FAKE_" + "TOKEN_VALUE"


def _write_cfg(path: Path, body: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def test_signed_in_email_and_no_secret_in_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "simon" / ".cursor" / "cli-config.json"
    _write_cfg(
        cfg,
        {"authInfo": {"email": "user@example.test", "accessToken": TOKEN, "refreshToken": TOKEN}},
    )
    monkeypatch.setenv("BOB_CURSOR_CLI_CONFIG_PATH", str(cfg))
    found = bobreport.read_cursor_account_label()
    assert found["status"] == "ok"
    assert found["email"] == "user@example.test"
    assert found["user"] == "simon"
    blob = json.dumps(found)
    assert TOKEN not in blob
    assert "accessToken" not in blob
    payload = bobreport.build_grok_account_merge_payload(
        "host-a",
        bobreport._CURSOR_FIELD_OMIT,
        cursor_account=found["email"],
        cursor_account_user=found["user"],
        cursor_account_source=None,
    )
    wire = json.dumps(payload)
    assert TOKEN not in wire
    assert payload["cursor_account"] == "user@example.test"
    assert payload["cursor_account_user"] == "simon"
    assert "grok_account" not in payload
    assert payload["cursor_account_source"] is None
    assert "cursor_account_source" in payload["cleared"]


def test_missing_login_publishes_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "Administrator" / ".cursor" / "cli-config.json"
    monkeypatch.setenv("BOB_CURSOR_CLI_CONFIG_PATH", str(missing))
    found = bobreport.read_cursor_account_label()
    assert found["status"] == "none"
    assert found["email"] == "none"
    assert found["user"] == "Administrator"
    bare = tmp_path / "empty.json"
    _write_cfg(bare, {"authInfo": {}})
    monkeypatch.setenv("BOB_CURSOR_CLI_CONFIG_PATH", str(bare))
    assert bobreport.read_cursor_account_label()["email"] == "none"


def test_bad_json_is_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tmp_path / "seat" / ".cursor" / "cli-config.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("BOB_CURSOR_CLI_CONFIG_PATH", str(bad))
    found = bobreport.read_cursor_account_label()
    assert found["status"] == "unknown"
    assert found["email"] is None


def test_marker_live_pid_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = tmp_path / "cursor-key-override.json"
    marker.write_text(
        json.dumps({"source": "api_key", "pid": 4242, "written_at": "2026-11-20T00:00:00Z", "key": TOKEN}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_CURSOR_KEY_OVERRIDE_PATH", str(marker))
    monkeypatch.setattr(bobreport, "_pid_is_alive", lambda pid: pid == 4242)
    assert bobreport.read_cursor_account_source() is None
    marker.write_text(
        json.dumps({"source": "api_key", "pid": 4242, "written_at": "2026-11-20T00:00:00Z"}),
        encoding="utf-8",
    )
    assert bobreport.read_cursor_account_source() == "api_key"
    monkeypatch.setattr(bobreport, "_pid_is_alive", lambda pid: False)
    assert bobreport.read_cursor_account_source() is None


def test_identity_merge_keeps_model_and_exports(tmp_path: Path) -> None:
    doc = {"machines": {}}
    bobreport._apply_merge_payload(
        doc,
        "host-a",
        {"op": "merge", "machine": "host-a", "id": "host-a", "model": "composer-2"},
    )
    bobreport._apply_merge_payload(
        doc,
        "host-a",
        {
            "op": "merge",
            "machine": "host-a",
            "id": "host-a",
            "cursor_account": "user@example.test",
            "cursor_account_user": "simon",
            "cursor_account_source": "api_key",
        },
    )
    ent = doc["machines"]["host-a"]
    assert ent["model"] == "composer-2"
    assert ent["cursor_account"] == "user@example.test"
    assert "cursor_account" not in bobreport._MERGE_PEER_FIELDS
    bobreport.save_digest(tmp_path, doc)
    raw = json.loads((tmp_path / "digest.json").read_text(encoding="utf-8"))
    again = bobreport._coerce_machine("host-a", raw["machines"]["host-a"])
    assert again["cursor_account"] == "user@example.test"
    assert again["model"] == "composer-2"
    exported = bobreport.export_machine_for_tray(tmp_path, "host-a", again)
    wire = json.dumps(exported)
    assert exported["cursor_account"] == "user@example.test"
    assert exported["cursor_account_user"] == "simon"
    assert exported["cursor_account_source"] == "api_key"
    assert TOKEN not in wire
    bobreport._apply_merge_payload(
        doc,
        "host-a",
        {
            "op": "merge",
            "machine": "host-a",
            "id": "host-a",
            "cursor_account": "none",
            "cursor_account_user": "Administrator",
            "cursor_account_source": None,
            "cleared": ["cursor_account_source"],
        },
    )
    ent = doc["machines"]["host-a"]
    assert ent["cursor_account"] == "none"
    assert ent["model"] == "composer-2"
    assert "cursor_account_source" not in ent


def _ps(script: str) -> str:
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert r.returncode == 0, (r.stdout or "") + "\n" + (r.stderr or "")
    return (r.stdout or "").strip()


@needs_ps
def test_tray_row_shows_account_and_keeps_stale() -> None:
    script = f"""
. '{HOVER}'
$meter = [pscustomobject]@{{
  remaining_pct = 46
  account = 'FAKE_a'
  fresh = $false
  fetched_at = '2026-11-20T00:00:00Z'
  period_end = '2026-11-21T12:00:00Z'
}}
$stale = Format-BobTrayXaiWeeklyRow -MachineId 'host-a' -XaiWeekly $meter -AsPublished -CursorAccount 'user@example.test' -CursorAccountUser 'simon'
$fresh = Format-BobTrayXaiWeeklyRow -MachineId 'host-a' -XaiWeekly $meter -AsPublished -CursorAccount 'user@example.test' -CursorAccountUser 'simon'
$none = Format-BobTrayXaiWeeklyRow -MachineId 'host-a' -XaiWeekly $meter -AsPublished -CursorAccount 'none' -CursorAccountUser 'Administrator'
$key = Format-BobTrayXaiWeeklyRow -MachineId 'host-a' -XaiWeekly $meter -AsPublished -CursorAccount 'user@example.test' -CursorAccountUser 'simon' -CursorAccountSource 'api_key'
$same = Format-BobTrayXaiWeeklyRow -MachineId 'host-a' -XaiWeekly $meter -AsPublished
Write-Output $stale.heading
Write-Output $none.heading
Write-Output $key.heading
Write-Output $same.heading
"""
    # fresh flag is false in $meter; second call is the same object (stale). Rebuild a fresh meter below.
    out = _ps(script)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert "46% left [stale]" in lines[0]
    assert lines[0].index("[stale]") < lines[0].index("cursor user@example.test (simon)")
    assert "cursor none (Administrator)" in lines[1]
    assert lines[2].endswith("cursor api_key")
    assert "user@example.test" not in lines[2]
    assert "cursor " not in lines[3]


@needs_ps
def test_tray_fresh_suffix() -> None:
    script = f"""
. '{HOVER}'
$meter = [pscustomobject]@{{
  remaining_pct = 46
  account = 'FAKE_a'
  fresh = $true
  fetched_at = '2026-11-20T00:00:00Z'
  period_end = '2026-11-21T12:00:00Z'
}}
$row = Format-BobTrayXaiWeeklyRow -MachineId 'host-a' -XaiWeekly $meter -AsPublished -CursorAccount 'user@example.test' -CursorAccountUser 'simon'
Write-Output $row.heading
"""
    heading = _ps(script)
    assert "[stale]" not in heading
    assert "cursor user@example.test (simon)" in heading
    assert "46% left" in heading
