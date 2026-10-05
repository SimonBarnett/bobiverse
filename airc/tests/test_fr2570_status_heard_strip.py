"""FR #2570: strip Halloy/bobtalk Heard: noise; STATUS DONE id= matches Invoke-AircRemote Wait."""
from __future__ import annotations

from pathlib import Path

import airc_console as ac
import airc_jobs as jobs
from repo_layout import ROOT

AIRC = ROOT / "airc" / "scripts"


def _read(name: str) -> str:
    return (AIRC / name).read_text(encoding="utf-8-sig")


def test_sanitize_strips_heard_and_nick_prefix():
    noisy = "@marchhare_console marchhare here. weekly=27. Heard: STATUS machine=m"
    assert ac.sanitize_console_operator_text(noisy) == "STATUS machine=m"
    assert ac.sanitize_console_operator_text("Heard: id=aabbccdd hostname") == "id=aabbccdd hostname"
    assert ac.sanitize_console_operator_text("STATUS") == "STATUS"
    assert ac.sanitize_console_operator_text("id=deadbeef Get-Date") == "id=deadbeef Get-Date"


def test_parse_job_verb_accepts_leading_id():
    parsed = jobs.parse_job_verb("id=aabbccdd STATUS")
    assert parsed is not None
    verb, kv = parsed
    assert verb == "STATUS"
    assert kv.get("id") == "aabbccdd"
    assert jobs.parse_job_verb("STATUS id=aabbccdd")[1].get("id") == "aabbccdd"


def test_status_emits_done_with_caller_id(tmp_path):
    (tmp_path / "bob").mkdir()
    (tmp_path / "bob" / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (tmp_path / "airc").mkdir()
    (tmp_path / "airc" / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (tmp_path / "jeeves").mkdir()
    (tmp_path / "jeeves" / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store, ai_root=tmp_path, machine="tm", airc_running=True)
    lines = proto.handle("bob-tm", "STATUS", {"id": "c25bd00e"})
    assert any(x.startswith("out id=c25bd00e seq=1 STATUS machine=tm") for x in lines)
    assert lines[-1] == "DONE id=c25bd00e exit=0"


def test_invoke_airc_remote_status_pins_id():
    t = _read("Invoke-AircRemote.ps1")
    assert "'Status'" in t
    assert "id={0} STATUS" in t
    assert "FR #2570" in t


def test_docs_warn_replyfile_must_be_ear_jsonl():
    skill = (ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md").read_text(
        encoding="utf-8-sig"
    )
    trouble = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
    ).read_text(encoding="utf-8-sig")
    blob = skill + "\n" + trouble
    assert "2570" in blob or "FR #2570" in blob
    assert "airc-replies.jsonl" in blob
    assert "Heard:" in blob or "Heard" in blob


def test_handle_raw_heard_status_routes_job_not_shell(tmp_path):
    (tmp_path / "bob").mkdir()
    (tmp_path / "bob" / "VERSION").write_text("1\n", encoding="utf-8")
    (tmp_path / "airc").mkdir()
    (tmp_path / "airc" / "VERSION").write_text("1\n", encoding="utf-8")
    (tmp_path / "jeeves").mkdir()
    (tmp_path / "jeeves" / "VERSION").write_text("1\n", encoding="utf-8")
    replies: list[str] = []
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(
        store,
        on_reply=lambda n, line: replies.append(line),
        ai_root=tmp_path,
        machine="tm",
        airc_running=True,
    )
    auth = ac.AuthPolicy(operators={"bob-tm"}, machine="tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        job_protocol=proto,
    )
    noisy = "@tm_console marchhare here. weekly=27. Heard: id=c25bd00e STATUS"
    hr = core.handle_raw(f":bob-tm!u@h PRIVMSG tm_console :{noisy}")
    assert hr is not None and hr.action == "job"
    assert any(r.startswith("out id=c25bd00e seq=1 STATUS machine=tm") for r in replies)
    assert any(r == "DONE id=c25bd00e exit=0" for r in replies)


def test_mrb2571_sanitize_bobtalk_prefix_without_heard():
    """MRB #2571: @nick mid here. weekly=N. STATUS (no Heard:) still strips to STATUS."""
    noisy = "@tm_console marchhare here. weekly=27. STATUS"
    assert ac.sanitize_console_operator_text(noisy) == "STATUS"
    assert not ac.sanitize_console_operator_text(
        "@tm_console marchhare here. weekly=27. Heard: Get-Date"
    ).startswith("@")


def test_mrb2571_status_without_caller_id_still_emits_done(tmp_path):
    """MRB #2571: STATUS with empty kv still ends DONE id=… exit=0 (generated id)."""
    for name in ("bob", "airc", "jeeves"):
        d = tmp_path / name
        d.mkdir()
        (d / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    store = jobs.JobStore(tmp_path / "home")
    proto = jobs.JobProtocol(store, ai_root=tmp_path, machine="tm", airc_running=True)
    lines = proto.handle("bob-tm", "STATUS", {})
    assert lines[0].startswith("out id=") and " seq=1 STATUS machine=tm" in lines[0]
    assert lines[-1].startswith("DONE id=") and lines[-1].endswith("exit=0")
    assert len(lines[-1].split("id=")[1].split()[0]) == 8


def test_mrb2571_skills_status_heard_bullet_contiguous():
    """MRB #2571: skill inserts are complete bullets (no orphan Heard: tail)."""
    skill = (ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md").read_text(
        encoding="utf-8-sig"
    )
    assert "STATUS + Heard: strip (FR #2570" in skill
    assert "#2575" in skill or "2575" in skill
    assert "sanitize_console_operator_text" in skill
    assert "Footgun" in skill or "footgun" in skill.lower()
    trouble = (
        ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"
    ).read_text(encoding="utf-8-sig")
    assert "-Action Status" in trouble or "Action Status" in trouble
    assert "FR #2570" in trouble

