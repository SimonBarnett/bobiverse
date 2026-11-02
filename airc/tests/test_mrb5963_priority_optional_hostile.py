"""docs/mrb-5963: hostile pins for Priority-optional (FR #5960 / PR #5963)."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_fail_intake as fail
import airc_priority as ap
from airc_auth_helpers import ops_auth


def _core(tmp_path: Path):
    auth = ops_auth("bob-walrus", channel="#walrus")
    root = tmp_path / "airc-install"
    (root / "config").mkdir(parents=True)
    return ac.AircConsoleCore(
        machine="walrus",
        auth=auth,
        nick="walrus_console",
        install_root=str(root),
    )


def test_mrb5963_example_only_is_not_runtime(tmp_path):
    root = tmp_path / "pkg"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    shipped = (
        Path(__file__).resolve().parents[1] / "config" / "priority-instances.example.json"
    )
    (cfg / "priority-instances.example.json").write_text(
        shipped.read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert ap.resolve_live_allowlist_path(root) is None
    assert ap.priority_runtime_available(root) is False
    assert ac.load_priority_instances(root) == []


def test_mrb5963_priority_absent_no_intake(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fail, "report_verb_failure", lambda *a, **k: calls.append(1) or None)
    core = _core(tmp_path)
    r = core.handle_raw(":bob-walrus!u@h PRIVMSG walrus_console :PRIORITY connect x")
    assert r is not None
    assert "priority_not_installed" in (r.reply or "")
    assert calls == []


def test_mrb5963_docs_live_only_loader_rules():
    doc = Path(__file__).resolve().parents[1] / "docs" / "airc-priority-client.md"
    text = doc.read_text(encoding="utf-8")
    assert "FR #5960" in text
    assert "never enables live PRIORITY" in text or "docs/tests only" in text
    assert "else example for docs/tests" not in text
    assert not doc.read_bytes().startswith(b"\xef\xbb\xbf")
