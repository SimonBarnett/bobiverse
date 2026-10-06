"""FR #2728: Jeeves !status uptime from process start, frozen VERSION, real busy seats."""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import chair_commands as cc
import irc_agent


def test_status_lines_uptime_from_earlier_started(tmp_path):
    started = time.time() - 42.5
    now = time.time()
    lines = cc.status_lines(tmp_path, started=started, now=now, version="9.9.9")
    assert lines[0].startswith("Jeeves status: version=9.9.9 uptime_s=")
    up = int(lines[0].split("uptime_s=")[1].split()[0])
    assert up >= 42
    assert up <= 50


def test_cc_uses_process_started_not_lazy_now(monkeypatch):
    """Agent construction time must drive uptime; first !status must not reset the clock."""
    agent = irc_agent.Client.__new__(irc_agent.Client)
    agent._process_started = time.time() - 10.0
    agent._cc_state = None
    st1 = agent._cc()
    t_a = st1.started
    time.sleep(0.05)
    st2 = agent._cc()
    assert st2 is st1
    assert st2.started == t_a
    assert time.time() - st2.started >= 10.0


def test_read_version_frozen_mei_falls_back_to_install_root(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_INSTALL_ROOT", raising=False)
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    monkeypatch.delenv("BOBIVERSE_VERSION", raising=False)
    monkeypatch.delenv("BOB_VERSION", raising=False)

    install = tmp_path / "ai" / "jeeves"
    (install / "jeeves").mkdir(parents=True)
    (install / "VERSION").write_text("1.2.3-fr2728\n", encoding="utf-8")
    exe = install / "jeeves" / "jeeves.exe"
    exe.write_bytes(b"MZ")

    mei = tmp_path / "_MEI00deadbeef"
    mei.mkdir()
    # No VERSION under MEIPASS — the bug class that yields version=?
    fake_file = mei / "chair_commands.pyc"
    fake_file.write_bytes(b"")

    got = cc.read_version(
        root=None,
        env={},
        frozen=True,
        executable=exe,
        file_path=fake_file,
        meipass=mei,
    )
    assert got == "1.2.3-fr2728"


def test_read_version_prefers_jeeves_install_root_env(tmp_path, monkeypatch):
    monkeypatch.delenv("BOBIVERSE_VERSION", raising=False)
    monkeypatch.delenv("BOB_VERSION", raising=False)
    install = tmp_path / "install"
    install.mkdir()
    (install / "VERSION").write_text("env-root-ver\n", encoding="utf-8")
    mei = tmp_path / "_MEI"
    mei.mkdir()
    (mei / "VERSION").write_text("bundled-wrong\n", encoding="utf-8")
    got = cc.read_version(
        env={"JEEVES_INSTALL_ROOT": str(install)},
        frozen=True,
        executable=tmp_path / "elsewhere" / "jeeves.exe",
        meipass=mei,
    )
    assert got == "env-root-ver"


def test_read_version_bundled_meipass_when_install_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_INSTALL_ROOT", raising=False)
    monkeypatch.delenv("BOB_INSTALL_ROOT", raising=False)
    monkeypatch.delenv("BOBIVERSE_VERSION", raising=False)
    monkeypatch.delenv("BOB_VERSION", raising=False)
    mei = tmp_path / "_MEIbundled"
    mei.mkdir()
    (mei / "VERSION").write_text("bundled-9\n", encoding="utf-8")
    exe = tmp_path / "orphan" / "jeeves.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    # orphan parent has no VERSION
    got = cc.read_version(env={}, frozen=True, executable=exe, meipass=mei, file_path=mei / "x.pyc")
    assert got == "bundled-9"


def test_status_lines_busy_counts_digest_doing_not_accepted(tmp_path):
    import registered_machines as rm

    # load_digest drops machines not on the ChanServ roster
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    # accepted queue empty, but digest has one doing seat
    digest = {
        "machines": {
            "marchhare": {
                "worker_list": [
                    {"nick": "marchhare-1", "state": "doing", "work": "FR #2705", "updated": time.time()},
                    {"nick": "marchhare-2", "state": "idle", "work": "", "updated": time.time()},
                ]
            }
        }
    }
    (tmp_path / "digest.json").write_text(json.dumps(digest), encoding="utf-8")
    lines = cc.status_lines(tmp_path, started=time.time() - 1, now=time.time(), version="1")
    assert lines[1].startswith("queue: unaccepted=")
    assert "accepted=0" in lines[1]
    assert lines[2] == "workers: busy=1"


def test_status_lines_busy_zero_when_no_doing(tmp_path):
    import registered_machines as rm

    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    digest = {
        "machines": {
            "marchhare": {
                "worker_list": [
                    {"nick": "marchhare-1", "state": "offered", "work": "MRB #1", "updated": time.time()},
                ]
            }
        }
    }
    (tmp_path / "digest.json").write_text(json.dumps(digest), encoding="utf-8")
    lines = cc.status_lines(tmp_path, started=time.time(), version="1")
    assert lines[2] == "workers: busy=0"


def test_docs_status_row_mentions_digest_doing():
    doc = Path(__file__).resolve().parents[1] / "docs" / "jeeves-commands.md"
    text = doc.read_text(encoding="utf-8")
    assert "!status" in text
    assert "uptime_s" in text
    assert "2728" in text
    assert "state=doing" in text or "state=doing" in text.replace("`", "")
    assert "accepted-queue" in text or "accepted-queue length" in text
