"""FR #5837: unknown PRIORITY fixture forms return a named bounded failure."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_fail_intake as fail
import airc_priority as ap
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"
QID = "c5837001"


def _allowlist(tmp_path: Path) -> Path:
    path = tmp_path / "priority-instances.json"
    path.write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "fixture",
                        "url": "https://example.invalid/priority",
                        "company": "live1",
                        "user": "u1",
                        "credentialTarget": "PriorityWeb/fixture",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _payload(result: ap.PriorityWalkResult) -> dict:
    out = result.lines[0]
    return json.loads(out.split("seq=1 ", 1)[1])


def test_unknown_form_returns_named_failure_with_form_name(tmp_path: Path):
    result = ap.run_priority_walk(
        text=f"id={QID} PRIORITY formStart instance=fixture form=CUSTOMERS",
        allowlist_path=_allowlist(tmp_path),
        fixture_path=FIX,
    )

    payload = _payload(result)
    assert result.ok is False
    assert result.exit_code == 2
    assert payload["error"] == "form-not-found"
    assert payload["form"] == "CUSTOMERS"
    assert "detail" not in payload
    assert "KeyError" not in result.lines[0]
    assert result.lines[-1] == f"DONE id={QID} exit=2"
    assert len(result.lines[0].encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES


def test_unknown_form_echo_is_bounded(tmp_path: Path):
    result = ap.run_priority_walk(
        text=f"id={QID} PRIORITY formStart instance=fixture form={'X' * 300}",
        allowlist_path=_allowlist(tmp_path),
        fixture_path=FIX,
    )
    payload = _payload(result)
    assert payload["error"] == "form-not-found"
    assert payload["form"].endswith("...")
    assert len(result.lines[0].encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES


def test_malformed_fixture_record_remains_fixture_miss(tmp_path: Path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"forms": {"CUST": None}}), encoding="utf-8")
    result = ap.run_priority_walk(
        text=f"id={QID} PRIORITY formStart instance=fixture form=CUST",
        allowlist_path=_allowlist(tmp_path),
        fixture_path=fixture,
    )
    assert result.payload["error"] == "fixture-miss"
    assert result.payload["detail"] == "KeyError"


def test_console_reports_unknown_form_once_via_fail_intake(tmp_path: Path, monkeypatch):
    posts: list[dict] = []
    monkeypatch.setattr(
        fail,
        "report_verb_failure",
        lambda verb, exc, **kwargs: posts.append(
            {"verb": verb, "exc": exc, "args": kwargs.get("args")}
        ),
    )
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=ops_auth("bob-marchhare", channel="#marchhare"),
        nick="marchhare_console",
        install_root=str(tmp_path),
        priority_allowlist=str(_allowlist(tmp_path)),
        priority_fixture=str(FIX),
    )

    result = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        f"id={QID} PRIORITY formStart instance=fixture form=CUSTOMERS"
    )

    assert result is not None and result.action == "priority"
    assert "form-not-found" in (result.reply or "")
    assert "KeyError" not in (result.reply or "")
    assert result.reply.count(f"DONE id={QID} exit=2") == 1
    assert len(posts) == 1
    assert posts[0]["verb"] == "priority"
    assert posts[0]["exc"] == "form-not-found"
    assert posts[0]["args"]["form"] == "CUSTOMERS"


def test_fail_intake_spool_preserves_redacted_args(tmp_path: Path, monkeypatch):
    spool = tmp_path / "spool"
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(spool))
    monkeypatch.setattr(fail, "intake_allowed", lambda **_kwargs: True)

    def offline(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(fail, "_native_post", offline)

    fail.report_verb_failure(
        "priority",
        "form-not-found",
        args={"form": "CUSTOMERS", "password": "do-not-store"},
        machine="marchhare",
        version="1.0.0",
        wait_s=0,
    )

    rows = list(spool.glob("*.json"))
    assert len(rows) == 1
    row = json.loads(rows[0].read_text(encoding="utf-8"))
    assert "CUSTOMERS" in row["body"]
    assert "do-not-store" not in row["body"]
