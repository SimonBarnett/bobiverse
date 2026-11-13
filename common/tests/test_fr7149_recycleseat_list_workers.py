"""FR #7149: digest workers[] list must not AttributeError into state_unavailable."""
from __future__ import annotations

import json
import os
from pathlib import Path

import bobreport
import recycleseat as rs
import startworker as sw

NOW = 1_800_000_200.0
SEAT = "redqueen-6240"


def _isolate(monkeypatch) -> None:
    monkeypatch.setenv("BOBIVERSE_BUILD_SUITE", "1")
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)


def _alive(install: Path) -> None:
    adir = sw.queue_dir(install)
    adir.mkdir(parents=True)
    for name in (sw.ALIVE_FILE, sw.ENGINE_ALIVE_FILE):
        path = adir / name
        path.write_text("alive")
        os.utime(path, (NOW, NOW))


def _ask(install, home, seat=SEAT, **kw):
    args = dict(
        body=f"!recycleseat {seat} redqueen",
        nick="Jeeves",
        account=None,
        channel="#redqueen",
        local_machine="redqueen",
        qdir=rs.queue_dir(install),
        install_root=install,
        home=home,
        machine_of_nick=bobreport.machine_from_nick,
        now=NOW,
    )
    args.update(kw)
    return rs.decide(**args)


def test_fr7149_list_workers_idle_is_known_not_busy(tmp_path, monkeypatch):
    """Live digest shape: machines.<mid>.workers is a list of {nick,state,work}."""
    _isolate(monkeypatch)
    install = tmp_path / "install"
    home = tmp_path / "home"
    home.mkdir()
    _alive(install)
    bobreport.save_digest(
        home,
        {
            "machines": {
                "redqueen": {
                    "workers": [
                        {"nick": SEAT, "state": "idle", "work": "", "updated": "2026-11-13T22:02:57Z"},
                        {
                            "nick": "redqueen-9160",
                            "state": "doing",
                            "work": "bobiverse FR #7149",
                            "updated": "2026-11-13T22:23:13Z",
                        },
                    ]
                }
            }
        },
    )
    known, working, err = rs.inspect_seat_work(home, SEAT, install)
    assert known is True, err
    assert working is False
    assert err == ""
    d = _ask(install, home)
    assert d.ok, (d.reason, d.line)
    assert list(rs.queue_dir(install).glob("req-*.json"))


def test_fr7149_list_workers_doing_is_busy(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    install = tmp_path / "install"
    home = tmp_path / "home"
    home.mkdir()
    _alive(install)
    bobreport.save_digest(
        home,
        {
            "machines": {
                "redqueen": {
                    "workers": [
                        {
                            "nick": SEAT,
                            "state": "doing",
                            "work": "FR SimonBarnett/bobiverse#7149",
                            "updated": "2026-11-13T22:23:13Z",
                        }
                    ]
                }
            }
        },
    )
    known, working, err = rs.inspect_seat_work(home, SEAT, install)
    assert known is True, err
    assert working is True
    d = _ask(install, home)
    assert not d.ok and d.reason == "busy"


def test_fr7149_dict_workers_pid_map_still_works(tmp_path, monkeypatch):
    """Regression: FR #7117 pid-keyed workers dict path stays valid."""
    _isolate(monkeypatch)
    install = tmp_path / "install"
    home = tmp_path / "home"
    home.mkdir()
    _alive(install)
    bobreport.save_digest(
        home,
        {"machines": {"redqueen": {"workers": {"6240": {"working_on": ""}}}}},
    )
    known, working, err = rs.inspect_seat_work(home, SEAT, install)
    assert known is True, err
    assert working is False
    d = _ask(install, home)
    assert d.ok, (d.reason, d.line)