"""FR #2522: Jeeves maintenance agent - butler icon + title, resume-vs-new, self-exit, harvest-before-exit."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from repo_layout import ROOT

import bob_worker as bw

SID = "11111111-2222-3333-4444-555555555555"
AGENTS = ROOT / "jeeves/AGENTS.md"
SKILL = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-troubleshooting/SKILL.md"


class FakeProc:
    def __init__(self, pid: int = 4321, exit_after: int | None = 0):
        self.pid = pid
        self.polls = 0
        self.exit_after = exit_after

    def poll(self):
        self.polls += 1
        if self.exit_after is not None and self.polls > self.exit_after:
            return 0
        return None


def _work(tmp_path: Path) -> Path:
    folder = tmp_path / "ai" / "jeeves"
    (folder / "assets").mkdir(parents=True)
    (folder / "AGENTS.md").write_text("# jeeves", encoding="utf-8")
    (folder / "assets" / "jeeves-butler.ico").write_bytes(b"\x00\x00\x01\x00")
    return folder


def _harness(tmp_path, monkeypatch, proc, *, kind="grok", state=None, sessions=None):
    folder = _work(tmp_path)
    monkeypatch.setattr(bw, "_choose", lambda *_a, **_k: (SimpleNamespace(kind=kind), "agent.cmd", "grok.exe", None))
    monkeypatch.setattr(bw, "install_ctrl_handler", lambda _cb: True)
    rec = {"titles": [], "icons": [], "spawned": [], "killed": [], "log": []}

    def log(msg):
        rec["log"].append(msg)

    def spawn(spec, env):
        rec["spawned"].append(spec)
        return proc

    run_dir = tmp_path / "run"
    kw = dict(
        spawn=spawn,
        poll_s=0.001,
        state_path=state or (tmp_path / "state" / "last-session.json"),
        sessions_root=sessions or (tmp_path / "sessions"),
        console=lambda title: rec["titles"].append(title) or True,
        icon_setter=lambda root, icon=None: rec["icons"].append((root, icon)) or True,
        killer=lambda pid: rec["killed"].append(pid) or True,
        run_dir=run_dir,
        acquire_mutex=lambda: True,
    )
    args = SimpleNamespace(work_root=str(folder), install_root=str(tmp_path / "ai" / "bob"))
    return folder, run_dir, args, log, kw, rec


# ---------------------------------------------------------------- icon + title
def test_fr2522_window_title_and_butler_icon_passed(tmp_path, monkeypatch):
    folder, _rd, args, log, kw, rec = _harness(tmp_path, monkeypatch, FakeProc(exit_after=0))
    assert bw.run_maintenance(args, log, **kw) == bw.EXIT_OK
    assert rec["titles"][0] == "Jeeves maintenance" == bw.MAINTENANCE_TITLE
    root, icon = rec["icons"][0]
    assert Path(icon) == folder / "assets" / "jeeves-butler.ico"
    assert Path(root) == folder


def test_fr2522_icon_path_prefers_work_root_butler(tmp_path):
    folder = _work(tmp_path)
    assert bw.maintenance_icon_path(folder) == folder / "assets" / "jeeves-butler.ico"


def test_fr2522_set_console_icon_accepts_explicit_icon(tmp_path):
    # never raises without a console; explicit icon kwarg is part of the contract
    assert bw.set_console_icon(tmp_path, icon=tmp_path / "x.ico") in (True, False)


# ---------------------------------------------------------------- resume vs new
def _state(tmp_path, cwd, sid=SID):
    sp = tmp_path / "state" / "last-session.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps({"session_id": sid, "cwd": str(cwd), "kind": "grok"}), encoding="utf-8")
    return sp


def _session_dir(tmp_path, cwd, sid=SID):
    from urllib.parse import quote

    d = tmp_path / "sessions" / quote(str(cwd), safe="") / sid
    d.mkdir(parents=True)
    return tmp_path / "sessions"


def test_fr2522_new_when_no_previous_session(tmp_path):
    how, sid = bw.choose_maintenance_session(r"C:\ai\jeeves", "grok", state_path=tmp_path / "none.json",
                                             sessions_root=tmp_path / "sessions")
    assert how == "new" and sid != SID and len(sid) == 36


def test_fr2522_resume_when_previous_session_exists(tmp_path):
    cwd = r"C:\ai\jeeves"
    how, sid = bw.choose_maintenance_session(cwd, "grok", state_path=_state(tmp_path, cwd),
                                             sessions_root=_session_dir(tmp_path, cwd))
    assert (how, sid) == ("resume", SID)


def test_fr2522_new_when_recorded_session_gone_or_other_cwd_or_cursor(tmp_path):
    cwd = r"C:\ai\jeeves"
    sp = _state(tmp_path, cwd)
    assert bw.choose_maintenance_session(cwd, "grok", state_path=sp, sessions_root=tmp_path / "empty")[0] == "new"
    roots = _session_dir(tmp_path, cwd)
    assert bw.choose_maintenance_session(r"D:\ai\jeeves", "grok", state_path=sp, sessions_root=roots)[0] == "new"
    assert bw.choose_maintenance_session(cwd, "cursor", state_path=sp, sessions_root=roots)[0] == "new"


def test_fr2522_build_launch_resume_only_for_grok_maintenance(tmp_path):
    spec = bw.build_launch("grok", "maintenance", r"C:\ai\jeeves", "p", "grok.exe", tmp_path, resume_session_id=SID)
    i = spec.argv.index("--resume")
    assert spec.argv[i + 1] == SID and "-s" not in spec.argv and spec.session_id == SID
    with pytest.raises(ValueError):
        bw.build_launch("grok", "agent", r"C:\ai\bob\worker", "p", "grok.exe", tmp_path, resume_session_id=SID)
    with pytest.raises(ValueError):
        bw.build_launch("grok", "monitor", r"C:\ai\jeeves", "p", "grok.exe", tmp_path, resume_session_id=SID)
    with pytest.raises(ValueError):
        bw.assert_fresh(["grok.exe", "--resume", SID])  # workers still refuse
    with pytest.raises(ValueError):
        bw.assert_fresh(["grok.exe", "--resume"], allow_resume=True)  # bare resume never allowed


def test_fr2522_run_maintenance_resumes_and_records(tmp_path, monkeypatch):
    proc = FakeProc(exit_after=0)
    folder, _rd, args, log, kw, rec = _harness(tmp_path, monkeypatch, proc)
    kw["state_path"] = _state(tmp_path, folder)
    kw["sessions_root"] = _session_dir(tmp_path, folder)
    bw.run_maintenance(args, log, **kw)
    argv = rec["spawned"][0].argv
    assert "--resume" in argv and SID in argv
    assert "RESUMES" in argv[-1]
    assert json.loads(kw["state_path"].read_text(encoding="utf-8"))["session_id"] == SID


def test_fr2522_run_maintenance_new_records_session(tmp_path, monkeypatch):
    folder, _rd, args, log, kw, rec = _harness(tmp_path, monkeypatch, FakeProc(exit_after=0))
    bw.run_maintenance(args, log, **kw)
    spec = rec["spawned"][0]
    assert "--resume" not in spec.argv and "-s" in spec.argv
    st = json.loads(kw["state_path"].read_text(encoding="utf-8"))
    assert st["session_id"] == spec.session_id and st["cwd"] == str(folder)


# ---------------------------------------------------------------- self-exit + harvest before exit
def _done(run_dir: Path, **fields):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / bw.MAINTENANCE_DONE_NAME).write_text(json.dumps(fields), encoding="utf-8")


def test_fr2522_self_exit_after_harvested_done_file(tmp_path, monkeypatch):
    proc = FakeProc(pid=777, exit_after=None)  # agent never exits by itself
    folder, run_dir, args, log, kw, rec = _harness(tmp_path, monkeypatch, proc)
    _done(run_dir, harvested=True, issues=["#1"], receipts_closed=True, skills=["x"])
    assert bw.run_maintenance(args, log, **kw) == bw.EXIT_OK
    assert rec["killed"] == [777]
    assert any("closing agent tree" in m for m in rec["log"])


def test_fr2522_no_exit_before_harvest(tmp_path, monkeypatch):
    proc = FakeProc(pid=778, exit_after=3)  # ends on its own after a few polls
    folder, run_dir, args, log, kw, rec = _harness(tmp_path, monkeypatch, proc)
    _done(run_dir, harvested=False, issues=[], receipts_closed=True)
    assert bw.run_maintenance(args, log, **kw) == bw.EXIT_OK
    assert rec["killed"] == []  # did NOT close on an un-harvested done file
    assert any("waiting for harvest" in m for m in rec["log"])
    assert any("agent ended" in m for m in rec["log"])


@pytest.mark.parametrize("done,verdict", [
    (None, "wait"),
    ({}, "wait"),
    ({"harvested": True, "receipts_closed": True}, "wait"),
    ({"harvested": True, "issues": [], "receipts_closed": False}, "wait"),
    ({"harvested": "yes", "issues": [], "receipts_closed": True}, "wait"),
    ({"harvested": True, "issues": [], "receipts_closed": True}, "exit"),
])
def test_fr2522_exit_decision_requires_harvest(done, verdict):
    assert bw.maintenance_exit_decision(done)[0] == verdict


def test_fr2522_prompt_orders_harvest_then_done_then_close():
    p = bw.maintenance_prompt(r"C:\ai\jeeves", done_file=r"C:\run\maintenance-done.json")
    a = p.index("harvest maintenance skills")
    b = p.index("ONLY THEN write")
    c = p.index("closes this window")
    assert a < b < c
    assert "close any receipt issue immediately" in p
    assert "NEW session only (never resume)" not in p
    assert "PR + MRB" in p and "never live-edit the running jeeves.exe" in p
    assert "RESUMES" in bw.maintenance_prompt(r"C:\ai\jeeves", resumed=True)


def test_fr2522_docs_agents_skills_updated():
    for path in (AGENTS, SKILL):
        t = path.read_text(encoding="utf-8")
        assert "#2522" in t and "Jeeves maintenance" in t
        assert "resumes" in t and "maintenance-done.json" in t
        assert "PR + MRB" in t and "jeeves/checks" in t


def test_fr2522_rate_limit_and_single_instance_unchanged():
    t = (ROOT / "common/scripts/jeeves_maintenance.py").read_text(encoding="utf-8")
    assert "MAINTENANCE_COOLDOWN_S = 30 * 60" in t
    assert "already_live" in t
