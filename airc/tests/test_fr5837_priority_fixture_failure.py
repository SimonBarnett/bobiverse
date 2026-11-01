"""FR #5837: fixture misses have named replies and shared fail-intake reporting."""
from __future__ import annotations

import json

import pytest

import airc_fail_intake as fi
import airc_priority as ap
from test_fr5285_priority_form_walk import FIX, _core


@pytest.mark.parametrize(
    ("command", "reason", "form", "path"),
    [
        ("formStart fixture CUSTOMERS", "form-not-found", "CUSTOMERS", ""),
        ("formStart instance=fixture form=CUSTOMERS", "form-not-found", "CUSTOMERS", ""),
        ("getRows fixture CUSTOMERS", "form-not-found", "CUSTOMERS", ""),
        ("subform fixture CUSTOMERS path=LINES", "form-not-found", "CUSTOMERS", "LINES"),
        ("subform fixture CUST path=UNKNOWN", "subform-not-found", "CUST", "UNKNOWN"),
    ],
)
def test_named_fixture_miss_reports_once_and_service_recovers(
    tmp_path, monkeypatch, command, reason, form, path
):
    allow = tmp_path / "priority-instances.json"
    allow.write_text('{"instances":[{"id":"fixture"}]}', encoding="utf-8")
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))
    core = _core(priority_allowlist=str(allow), priority_fixture=str(FIX))

    result = core.handle_raw(
        f":bob-marchhare!u@h PRIVMSG marchhare_console :id=aabbccdd PRIORITY {command}"
    )
    assert result and result.action == "priority"
    lines = result.reply.splitlines()
    assert len(lines) == 2
    assert lines[-1] == "DONE id=aabbccdd exit=2"
    body = json.loads(lines[0].split(" ", 3)[-1])
    assert body == {
        "ok": False, "error": reason, "form": form, "action": "walk",
        **({"path": path} if reason == "subform-not-found" else {}),
    }
    assert "KeyError" not in result.reply
    assert "detail" not in body
    assert len(reports) == 1
    args, kwargs = reports[0]
    assert args == ("priority", reason)
    assert kwargs["args"] == {
        "op": command.split()[0], "instance": "fixture", "form": form, "path": path,
    }
    assert kwargs["wait_s"] == 1.0

    recovered = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :id=bbccddee PRIORITY formStart fixture CUST"
    )
    assert recovered and recovered.reply.endswith("DONE id=bbccddee exit=0")
    assert len(reports) == 1


@pytest.mark.parametrize("contents", [None, "not-json", '{"forms":[]}'])
def test_fixture_load_failure_hides_exception_and_reports(tmp_path, monkeypatch, contents):
    allow = tmp_path / "priority-instances.json"
    allow.write_text('{"instances":[{"id":"fixture"}]}', encoding="utf-8")
    fixture = tmp_path / "fixture.json"
    if contents is not None:
        fixture.write_text(contents, encoding="utf-8")
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))
    result = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart fixture CUST",
        allowlist_path=allow,
        fixture_path=fixture,
    )
    assert result.payload == {"ok": False, "error": "fixture-miss", "action": "walk"}
    assert not result.ok and result.exit_code == 2
    assert result.lines[-1] == "DONE id=aabbccdd exit=2"
    assert len(reports) == 1
    assert reports[0][0][0] == "priority"
    assert isinstance(reports[0][0][1], Exception)


def test_reporting_failure_preserves_named_reply(tmp_path, monkeypatch):
    allow = tmp_path / "priority-instances.json"
    allow.write_text('{"instances":[{"id":"fixture"}]}', encoding="utf-8")

    def broken_report(*_a, **_kw):
        raise RuntimeError("intake-unavailable")

    monkeypatch.setattr(fi, "report_verb_failure", broken_report)
    result = ap.run_priority_walk(
        text="id=aabbccdd PRIORITY formStart fixture CUSTOMERS",
        allowlist_path=allow,
        fixture_path=FIX,
    )
    assert result.payload["error"] == "form-not-found"
    assert result.payload["form"] == "CUSTOMERS"
    assert result.lines[-1] == "DONE id=aabbccdd exit=2"
