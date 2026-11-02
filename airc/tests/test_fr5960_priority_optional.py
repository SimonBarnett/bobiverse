"""FR #5960: airc works with no Priority install; PRIORITY refuses cleanly."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_fail_intake as fail
import airc_priority as ap
from airc_auth_helpers import ops_auth


def _core(tmp_path: Path, **kw):
    auth = ops_auth("bob-walrus", channel="#walrus")
    root = tmp_path / "airc-install"
    root.mkdir()
    (root / "config").mkdir()
    return ac.AircConsoleCore(
        machine="walrus",
        auth=auth,
        nick="walrus_console",
        install_root=str(root),
        **kw,
    )


def test_fr5960_probe_absent_without_live_allowlist(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    (root / "config").mkdir()
    assert ap.priority_runtime_available(root) is False
    assert ap.priority_absent_reason(root) == "priority_not_installed"


def test_fr5960_probe_present_with_live_allowlist(tmp_path):
    root = tmp_path / "with"
    (root / "config").mkdir(parents=True)
    al = root / "config" / "priority-instances.json"
    al.write_text(
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
    assert ap.priority_runtime_available(root) is True


def test_fr5960_non_priority_verbs_ok_without_priority(tmp_path):
    core = _core(tmp_path)
    # Example allowlist must not auto-enable Priority on a clean install.
    r = core.handle_raw(":bob-walrus!u@h PRIVMSG walrus_console :VERSION")
    assert r is not None
    assert r.action in {"version", "shell", "pipe", "status"}
    r2 = core.handle_raw(":bob-walrus!u@h PRIVMSG walrus_console :STATUS")
    assert r2 is not None
    assert r2.action in {"status", "shell", "pipe", "version"}


def test_fr5960_priority_verb_refuses_without_intake(tmp_path, monkeypatch):
    calls = []

    def _spy(*a, **k):
        calls.append((a, k))
        return None

    monkeypatch.setattr(fail, "report_verb_failure", _spy)
    core = _core(tmp_path)
    r = core.handle_raw(":bob-walrus!u@h PRIVMSG walrus_console :PRIORITY status")
    assert r is not None
    assert r.action == "priority"
    blob = (r.reply or "")
    assert "priority_not_installed" in blob
    assert calls == []


def test_fr5960_priority_prepare_refuses_without_intake(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fail, "report_verb_failure", lambda *a, **k: calls.append(1) or None)
    core = _core(tmp_path)
    r = core.handle_raw(
        ":bob-walrus!u@h PRIVMSG walrus_console :PRIORITY prepare WWWSHOWCUST"
    )
    assert r is not None
    assert "priority_not_installed" in (r.reply or "")
    assert calls == []


def test_fr5960_example_allowlist_is_not_live(tmp_path):
    """Shipped example.json must not count as Priority installed."""
    root = tmp_path / "pkg"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    # Only example present (mirrors pack layout without live json).
    ex = cfg / "priority-instances.example.json"
    ex.write_text(
        (Path(__file__).resolve().parents[1] / "config" / "priority-instances.example.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    assert ap.priority_runtime_available(root) is False
    r = ap.run_priority_verb("status", None, job_id="abcd1234", install_root=root)
    assert r.ok is False
    text = " ".join(r.reply_lines())
    assert "priority_not_installed" in text
