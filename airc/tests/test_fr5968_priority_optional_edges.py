"""FR #5968: Priority optional edges after #5960."""
from __future__ import annotations

import json
from pathlib import Path

import airc_priority as ap


def test_fr5968_empty_instances_not_runtime_available(tmp_path):
    root = tmp_path / "empty-inst"
    (root / "config").mkdir(parents=True)
    (root / "config" / "priority-instances.json").write_text(
        json.dumps({"instances": []}), encoding="utf-8"
    )
    assert ap.priority_runtime_available(root) is False
    r = ap.run_priority_verb("status", None, job_id="abcd1234", install_root=root)
    assert r.ok is False
    text = " ".join(r.reply_lines())
    assert "priority_not_installed" in text or "priority_allowlist_empty" in text


def test_fr5968_schema_missing_field_stays_distinct(tmp_path):
    root = tmp_path / "bad-schema"
    (root / "config").mkdir(parents=True)
    live = root / "config" / "priority-instances.json"
    live.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "dev1",
                        "url": "https://prioritydev.example.invalid",
                        "company": "c",
                        "user": "u",
                        # credentialTarget intentionally omitted
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    # File exists with a row -> probe may be True after load attempt; verb must not map to not_installed
    r = ap.run_priority_verb(
        "status", None, job_id="abcd1234", install_root=root, allowlist_path=live
    )
    assert r.ok is False
    text = " ".join(r.reply_lines())
    assert "priority_not_installed" not in text
    assert "credentialTarget" in text or "missing" in text.lower()


def test_fr5968_product_root_live_json_without_install_root(tmp_path, monkeypatch):
    """When install_root is None, still find live json under the airc product root."""
    # Point product root at tmp by monkeypatching Path resolution helper if exposed,
    # else write into the real package config briefly is unsafe --- use monkeypatch on resolve.
    live_root = tmp_path / "airc-product"
    cfg = live_root / "config"
    cfg.mkdir(parents=True)
    live = cfg / "priority-instances.json"
    live.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "dev1",
                        "url": "https://prioritydev.example.invalid",
                        "company": "c",
                        "user": "u",
                        "credentialTarget": "t",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ap,
        "_product_airc_root",
        lambda: live_root,
    )
    assert ap.resolve_live_allowlist_path(None) == live
    assert ap.priority_runtime_available(None) is True
