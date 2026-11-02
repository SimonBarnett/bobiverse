"""FR #5535 / #5960: docs resolve may use example; live walk does not."""
from __future__ import annotations

import json
from pathlib import Path

import airc_priority as ap
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"
EXAMPLE = ROOT / "airc" / "config" / "priority-instances.example.json"


def test_fr5535_docs_resolve_falls_back_to_example_walk_live_only(tmp_path):
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    example = cfg / "priority-instances.example.json"
    example.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "example-dev",
                        "url": "https://prioritydev.example.invalid",
                        "company": "live1",
                        "user": "api-user",
                        "credentialTarget": "PriorityWeb/example-dev",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert not (cfg / "priority-instances.json").exists()
    status_path = ap.resolve_allowlist_path(root)
    walk_path = ap.resolve_walk_allowlist_path(str(root), None)
    assert status_path == example
    # FR #5960: walk/connect never treat example.json as installed Priority.
    assert walk_path is None


def test_fr5535_explicit_example_override_still_walks(tmp_path):
    """Tests/docs may pass example path explicitly; that is an override, not auto-fallback."""
    path = EXAMPLE
    assert path.is_file()
    r = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart instance=example-dev form=CUST",
        allowlist_path=path,
        fixture_path=FIX,
    )
    assert r.ok is True
    assert r.exit_code == 0
    assert "unknown-instance" not in "\n".join(r.lines)


def test_fr5535_live_json_still_wins(tmp_path):
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "priority-instances.example.json").write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "example-dev",
                        "url": "https://prioritydev.example.invalid",
                        "company": "live1",
                        "user": "api-user",
                        "credentialTarget": "PriorityWeb/example-dev",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    live = cfg / "priority-instances.json"
    live.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "live-only",
                        "url": "https://priority.example.invalid",
                        "company": "c",
                        "user": "u",
                        "credentialTarget": "PriorityWeb/live",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert ap.resolve_allowlist_path(root) == live
    assert ap.resolve_walk_allowlist_path(str(root), None) == live
