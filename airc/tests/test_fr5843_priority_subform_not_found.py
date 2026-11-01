"""FR #5843: unknown PRIORITY subform paths return a bounded named error."""
from __future__ import annotations

import json

import airc_fail_intake as fi
import airc_priority as ap
from repo_layout import ROOT


FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"


def _allowlist(tmp_path):
    allow = tmp_path / "priority-instances.json"
    allow.write_text(
        '{"instances":[{"id":"fixture","url":"https://prioritydev.example.invalid",'
        '"company":"c","user":"u","credentialTarget":"t"}]}',
        encoding="utf-8",
    )
    return allow


def test_unknown_subform_path_is_named_bounded_and_reported(tmp_path, monkeypatch):
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))

    result = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY subform instance=fixture form=CUST path=UNKNOWN",
        allowlist_path=_allowlist(tmp_path),
        fixture_path=FIX,
    )

    assert not result.ok
    assert result.exit_code == 2
    assert result.lines[-1] == "DONE id=aabbccdd exit=2"
    body = json.loads(result.lines[0].split(" ", 3)[-1])
    assert body == {
        "ok": False,
        "error": "subform-not-found",
        "form": "CUST",
        "path": "UNKNOWN",
        "action": "walk",
    }
    assert "KeyError" not in result.lines[0]
    assert "detail" not in body
    assert len(reports) == 1
    assert reports[0] == (
        ("priority", "subform-not-found"),
        {"args": {"op": "subform"}, "wait_s": 1.0},
    )


def test_unknown_subform_path_echo_is_bounded_even_if_intake_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fi,
        "report_verb_failure",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("intake unavailable")),
    )
    path = "x" * 200

    result = ap.run_priority_walk(
        text=f"id=aabbccdd PRIORITY subform instance=fixture form=CUST path={path}",
        allowlist_path=_allowlist(tmp_path),
        fixture_path=FIX,
    )

    assert result.exit_code == 2
    assert result.lines[-1] == "DONE id=aabbccdd exit=2"
    assert len(result.lines[0].encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(result.lines[0].split(" ", 3)[-1])
    assert body["error"] == "subform-not-found"
    assert body["path"].startswith("x")
    assert body["path"].endswith("...")
    assert "KeyError" not in result.lines[0]
