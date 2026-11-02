"""docs/mrb-5972: hostile pins for FR #5968 Priority optional edges (PR #5972)."""
from __future__ import annotations

import json

import airc_priority as ap


def test_mrb5972_empty_instances_exact_allowlist_empty_reason(tmp_path):
    root = tmp_path / "empty"
    (root / "config").mkdir(parents=True)
    (root / "config" / "priority-instances.json").write_text(
        json.dumps({"instances": []}), encoding="utf-8"
    )
    assert ap.priority_runtime_available(root) is False
    r = ap.run_priority_verb("status", None, job_id="abcd1234", install_root=root)
    assert r.ok is False
    text = " ".join(r.reply_lines())
    assert "priority_allowlist_empty" in text
    assert "priority_not_installed" not in text


def test_mrb5972_schema_missing_not_absent_or_empty(tmp_path):
    root = tmp_path / "schema"
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
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert ap._is_allowlist_absent_error(
        ap.PriorityConfigError("instances[0] missing credentialTarget")
    ) is False
    r = ap.run_priority_verb(
        "status", None, job_id="abcd1234", install_root=root, allowlist_path=live
    )
    text = " ".join(r.reply_lines())
    assert "priority_not_installed" not in text
    assert "priority_allowlist_empty" not in text
    assert "credentialTarget" in text or "missing" in text.lower()


def test_mrb5972_absent_error_classifier_pins():
    assert ap._is_allowlist_absent_error(ap.PriorityConfigError("allowlist instances empty"))
    assert ap._is_allowlist_absent_error(
        ap.PriorityConfigError("priority-instances allowlist missing")
    )
    assert not ap._is_allowlist_absent_error(
        ap.PriorityConfigError("instances[0] missing credentialTarget")
    )
