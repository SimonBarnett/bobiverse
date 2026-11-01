"""FR #5837: unknown PRIORITY formStart form -> form-not-found (no KeyError leak)."""
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


def _allowlist(tmp_path: Path, *, ids: list[str] | None = None) -> Path:
    rows = []
    for i in ids or ["fixture"]:
        rows.append(
            {
                "id": i,
                "url": "https://example.invalid/priority",
                "company": "live1",
                "user": "u1",
                "credentialTarget": f"PriorityWeb/{i}",
            }
        )
    path = tmp_path / "priority-instances.json"
    path.write_text(json.dumps({"instances": rows}), encoding="utf-8")
    return path


def _out_and_done(lines: tuple[str, ...] | list[str]) -> tuple[str, str]:
    clean = [ln for ln in lines if str(ln).strip()]
    assert len(clean) >= 2, lines
    assert clean[-1].startswith("DONE ")
    return clean[0], clean[-1]


def test_fr5837_customers_form_not_found(tmp_path: Path):
    allow = _allowlist(tmp_path)
    r = ap.run_priority_walk(
        text=f"id={QID} PRIORITY formStart instance=fixture form=CUSTOMERS",
        allowlist_path=allow,
        fixture_path=FIX,
    )
    assert r.ok is False
    assert r.exit_code == 2
    out, done = _out_and_done(r.lines)
    assert out.startswith(f"out id={QID} seq=1 ")
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("error") == "form-not-found"
    assert body.get("form") == "CUSTOMERS"
    assert "detail" not in body
    assert "KeyError" not in out
    assert "KeyError" not in done
    assert done == f"DONE id={QID} exit=2"
    assert r.payload.get("error") == "form-not-found"


def test_fr5837_case_sensitive_cust_miss_cust_hit(tmp_path: Path):
    allow = _allowlist(tmp_path)
    miss = ap.run_priority_walk(
        text=f"id={QID} PRIORITY formStart instance=fixture form=cust",
        allowlist_path=allow,
        fixture_path=FIX,
    )
    assert miss.payload.get("error") == "form-not-found"
    assert miss.payload.get("form") == "cust"
    assert miss.exit_code == 2

    hit = ap.run_priority_walk(
        text=f"id={QID} PRIORITY formStart instance=fixture form=CUST",
        allowlist_path=allow,
        fixture_path=FIX,
    )
    assert hit.ok is True
    assert hit.exit_code == 0
    assert hit.payload.get("ok") is True
    assert hit.payload.get("form") == "CUST"


def test_fr5837_long_form_name_bounded(tmp_path: Path):
    allow = _allowlist(tmp_path)
    huge = "\u20ac" * 300
    r = ap.run_priority_walk(
        text=f"id={QID} PRIORITY formStart instance=fixture form={huge}",
        allowlist_path=allow,
        fixture_path=FIX,
    )
    out, done = _out_and_done(r.lines)
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("error") == "form-not-found"
    assert str(body.get("form") or "").endswith("...")
    assert done == f"DONE id={QID} exit=2"
    assert r.exit_code == 2


def test_fr5837_missing_subform_still_fixture_miss(tmp_path: Path):
    allow = _allowlist(tmp_path)
    r = ap.run_priority_walk(
        text=(
            f"id={QID} PRIORITY subform instance=fixture form=CUST "
            "path=no-such-subform"
        ),
        allowlist_path=allow,
        fixture_path=FIX,
    )
    assert r.payload.get("error") == "fixture-miss"
    assert r.payload.get("detail") == "KeyError"
    assert r.exit_code == 2


def test_fr5837_fixture_without_forms_fixture_miss(tmp_path: Path):
    allow = _allowlist(tmp_path)
    bad = tmp_path / "empty-fixture.json"
    bad.write_text(json.dumps({"not_forms": {}}), encoding="utf-8")
    r = ap.run_priority_walk(
        text=f"id={QID} PRIORITY formStart instance=fixture form=CUST",
        allowlist_path=allow,
        fixture_path=bad,
    )
    assert r.payload.get("error") == "fixture-miss"
    assert r.payload.get("detail") == "ValueError"


def _console_core(tmp_path: Path, *, fixture: Path = FIX):
    class StubJobs:
        def __init__(self) -> None:
            self.emits: list[tuple[str, str]] = []

        def _emit(self, nick: str, line: str) -> None:
            self.emits.append((nick, line))

    allow = _allowlist(tmp_path)
    jobs = StubJobs()
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=ops_auth("bob-marchhare", channel="#marchhare"),
        nick="marchhare_console",
        install_root=str(tmp_path),
        priority_allowlist=str(allow),
        priority_fixture=str(fixture),
        job_protocol=jobs,  # type: ignore[arg-type]
    )
    return core, jobs


def test_fr5837_console_reports_form_not_found_once(tmp_path: Path, monkeypatch):
    posts: list[dict] = []

    def capture(verb, exc, **kw):
        posts.append({"verb": verb, "exc": exc, **kw})
        return {"ok": True}

    monkeypatch.setattr(fail, "report_verb_failure", capture)
    core, jobs = _console_core(tmp_path)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        f"id={QID} PRIORITY formStart instance=fixture form=CUSTOMERS"
    )
    assert hr and hr.action == "priority"
    lines = [ln for ln in (hr.reply or "").splitlines() if ln.strip()]
    assert sum(1 for ln in lines if ln.startswith(f"out id={QID}")) == 1
    assert sum(1 for ln in lines if ln.startswith(f"DONE id={QID} exit=2")) == 1
    assert "KeyError" not in (hr.reply or "")
    assert "form-not-found" in (hr.reply or "")
    assert jobs.emits == []
    assert len(posts) == 1
    assert posts[0]["verb"] == "priority"
    assert posts[0]["exc"] == "form-not-found"
    args = posts[0].get("args") or {}
    assert args.get("form") == "CUSTOMERS"
    assert args.get("action") == "walk"
    for k in args:
        assert "pass" not in k.lower()
        assert "secret" not in k.lower()
        assert "token" not in k.lower()


def test_fr5837_console_no_report_on_success_or_subform_miss(
    tmp_path: Path, monkeypatch
):
    posts: list[dict] = []
    monkeypatch.setattr(
        fail,
        "report_verb_failure",
        lambda *a, **k: posts.append({"a": a, "k": k}) or {"ok": True},
    )
    core, _jobs = _console_core(tmp_path)
    ok = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        f"id={QID} PRIORITY formStart instance=fixture form=CUST"
    )
    assert ok and "DONE id=" in (ok.reply or "") and "exit=0" in (ok.reply or "")
    miss = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        f"id={QID} PRIORITY subform instance=fixture form=CUST path=missing"
    )
    assert miss and "fixture-miss" in (miss.reply or "")
    assert posts == []


def test_fr5837_reporter_raise_does_not_change_reply(tmp_path: Path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("intake-down")

    monkeypatch.setattr(fail, "report_verb_failure", boom)
    core, jobs = _console_core(tmp_path)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        f"id={QID} PRIORITY formStart instance=fixture form=CUSTOMERS"
    )
    assert hr and hr.action == "priority"
    assert "form-not-found" in (hr.reply or "")
    assert "DONE id=" in (hr.reply or "") and "exit=2" in (hr.reply or "")
    assert jobs.emits == []
