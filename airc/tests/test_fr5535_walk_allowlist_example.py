"""FR #5535: PRIORITY walk uses the same allowlist fallback as status."""
from __future__ import annotations

import json
from pathlib import Path

import airc_priority as ap
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"
EXAMPLE = ROOT / "airc" / "config" / "priority-instances.example.json"


def test_fr5535_walk_resolve_falls_back_to_example(tmp_path):
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
    assert walk_path == example


def test_fr5535_walk_example_dev_not_unknown(tmp_path):
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    example = cfg / "priority-instances.example.json"
    example.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    path = ap.resolve_walk_allowlist_path(str(root), None)
    assert path is not None
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
