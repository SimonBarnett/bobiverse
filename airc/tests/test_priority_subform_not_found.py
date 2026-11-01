"""FR #5843: unknown PRIORITY subform path -> subform-not-found (no KeyError leak)."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_fail_intake as fail
import airc_priority as ap
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

FIX = ROOT / "airc" / "priority-worker" / "fixtures" / "form_walk.json"
QID = "c5843001"


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


def _out_and_done(lines) -> tuple[str, str]:
    clean = [ln for ln in lines if str(ln).strip()]
    assert len(clean) >= 2, lines
    assert clean[-1].startswith("DONE ")
    return clean[0], clean[-1]


def test_fr5843_unknown_path_subform_not_found(tmp_path: Path):
    allow = _allowlist(tmp_path)
    r = ap.run_priority_walk(
        text=(
            f"id={QID} PRIORITY subform instance=fixture form=CUST "
            "path=no-such-subform"
        ),
        allowlist_path=allow,
        fixture_path=FIX,
    )
    assert r.ok is False
    assert r.exit_code == 2
    out, done = _out_and_done(r.lines)
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("error") == "subform-not-found"
    assert body.get("path") == "no-such-subform"
    assert body.get("form") == "CUST"
    assert "detail" not in body
    assert "KeyError" not in out
    assert "KeyError" not in done
    assert done == f"DONE id={QID} exit=2"


def test_fr5843_known_subform_still_ok(tmp_path: Path):
    allow = _allowlist(tmp_path)
    r = ap.run_priority_walk(
        text=f"id={QID} PRIORITY subform instance=fixture form=CUST path=LINES",
        allowlist_path=allow,
        fixture_path=FIX,
    )
    assert r.ok is True
    assert r.exit_code == 0
    assert r.payload.get("path") == "LINES"


def test_fr5843_long_path_bounded(tmp_path: Path):
    allow = _allowlist(tmp_path)
    huge = "\u20ac" * 300
    r = ap.run_priority_walk(
        text=f"id={QID} PRIORITY subform instance=fixture form=CUST path={huge}",
        allowlist_path=allow,
        fixture_path=FIX,
    )
    out, done = _out_and_done(r.lines)
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("error") == "subform-not-found"
    assert str(body.get("path") or "").endswith("...")
    assert done == f"DONE id={QID} exit=2"


def test_fr5843_unknown_form_still_fixture_miss_on_main(tmp_path: Path):
    """Until FR #5837 merges, unknown form stays fixture-miss; do not broaden this tip."""
    allow = _allowlist(tmp_path)
    r = ap.run_priority_walk(
        text=f"id={QID} PRIORITY formStart instance=fixture form=CUSTOMERS",
        allowlist_path=allow,
        fixture_path=FIX,
    )
    # Accept either pre-#5837 fixture-miss or post-#5837 form-not-found.
    err = r.payload.get("error")
    assert err in ("fixture-miss", "form-not-found")
    if err == "fixture-miss":
        assert r.payload.get("detail") == "KeyError"


def _console_core(tmp_path: Path):
    class StubJobs:
        def __init__(self) -> None:
            self.emits: list[tuple[str, str]] = []

        def _emit(self, nick: str, line: str) -> None:
            self.emits.append((nick, line))

    jobs = StubJobs()
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=ops_auth("bob-marchhare", channel="#marchhare"),
        nick="marchhare_console",
        install_root=str(tmp_path),
        priority_allowlist=str(_allowlist(tmp_path)),
        priority_fixture=str(FIX),
        job_protocol=jobs,  # type: ignore[arg-type]
    )
    return core, jobs


def test_fr5843_console_reports_once(tmp_path: Path, monkeypatch):
    posts: list[dict] = []

    def capture(verb, exc, **kw):
        posts.append({"verb": verb, "exc": exc, **kw})
        return {"ok": True}

    monkeypatch.setattr(fail, "report_verb_failure", capture)
    core, jobs = _console_core(tmp_path)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        f"id={QID} PRIORITY subform instance=fixture form=CUST path=missing"
    )
    assert hr and hr.action == "priority"
    assert "subform-not-found" in (hr.reply or "")
    assert "KeyError" not in (hr.reply or "")
    assert sum(1 for ln in (hr.reply or "").splitlines() if ln.startswith(f"out id={QID}")) == 1
    assert sum(1 for ln in (hr.reply or "").splitlines() if f"DONE id={QID} exit=2" in ln) == 1
    assert jobs.emits == []
    assert len(posts) == 1
    assert posts[0]["verb"] == "priority"
    assert posts[0]["exc"] == "subform-not-found"
    args = posts[0].get("args") or {}
    assert args.get("path") == "missing"
    assert args.get("form") == "CUST"
    for k in args:
        assert "pass" not in k.lower()
        assert "secret" not in k.lower()
        assert "token" not in k.lower()


def test_fr5843_console_no_report_on_success(tmp_path: Path, monkeypatch):
    posts: list = []
    monkeypatch.setattr(
        fail,
        "report_verb_failure",
        lambda *a, **k: posts.append(1) or {"ok": True},
    )
    core, _jobs = _console_core(tmp_path)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        f"id={QID} PRIORITY subform instance=fixture form=CUST path=LINES"
    )
    assert hr and "exit=0" in (hr.reply or "")
    assert posts == []


def test_fr5843_reporter_raise_keeps_reply(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        fail, "report_verb_failure", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x"))
    )
    core, jobs = _console_core(tmp_path)
    hr = core.handle_raw(
        ":bob-marchhare!u@h PRIVMSG marchhare_console :"
        f"id={QID} PRIORITY subform instance=fixture form=CUST path=missing"
    )
    assert hr and "subform-not-found" in (hr.reply or "") and "exit=2" in (hr.reply or "")
    assert jobs.emits == []
