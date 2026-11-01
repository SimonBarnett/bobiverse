"""MRB #5862: priority allowlist reader tolerates UTF-8 BOM."""
from __future__ import annotations

import json
from pathlib import Path

import airc_priority as ap


def test_mrb5862_load_allowlist_rows_accepts_utf8_bom(tmp_path: Path):
    path = tmp_path / "priority-instances.json"
    payload = {
        "instances": [
            {
                "id": "hrs-dev-live1",
                "url": "https://priority.example.invalid",
                "company": "live1",
                "user": "Tabula",
                "credentialTarget": "PriorityWeb/hrs-priority-dev",
            }
        ]
    }
    raw = b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")
    path.write_bytes(raw)

    rows = ap.load_allowlist_rows(path)
    assert len(rows) == 1
    assert rows[0]["id"] == "hrs-dev-live1"
    assert rows[0]["credentialTarget"] == "PriorityWeb/hrs-priority-dev"


def test_mrb5862_allowlisted_cred_targets_with_bom(tmp_path: Path):
    import airc_cred_irc as circ

    path = tmp_path / "priority-instances.json"
    payload = {
        "instances": [
            {
                "id": "hrs-dev-live1",
                "credentialTarget": "PriorityWeb/hrs-priority-dev",
            }
        ]
    }
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    targets = circ.allowlisted_cred_targets(str(path))
    assert "PriorityWeb/hrs-priority-dev" in targets
