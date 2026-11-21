"""FR #8602: !recycleseat --force when stuck (stale updated / accepted_silent).

Hung OpenCode seats stay busy in digest and cannot GIVEUP; busy gate blocked
ops recycle. Force is allowed only when the seat looks stuck.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import bobreport
import recycleseat as rs
import startworker as sw

NOW = 1_800_000_000.0
SEAT = "flamingo-16764"


def _iso_age(age_s: float) -> str:
    ts = datetime.fromtimestamp(NOW - age_s, tz=timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def setup_env(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_RECYCLESEAT_DISABLE", raising=False)
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    monkeypatch.delenv("BOB_RECYCLESEAT_STUCK_S", raising=False)
    install = tmp_path / "install"
    home = tmp_path / "home"
    home.mkdir()
    (home / "registered-machines.json").write_text(
        json.dumps({"machines": ["flamingo", "marchhare"]})
    )
    adir = sw.queue_dir(install)
    adir.mkdir(parents=True)
    for name in (sw.ALIVE_FILE, sw.ENGINE_ALIVE_FILE):
        path = adir / name
        path.write_text("alive")
        os.utime(path, (NOW, NOW))
    return install, home


def ask(install, home, body: str, **kw):
    args = dict(
        body=body,
        nick="Jeeves",
        account=None,
        channel="#flamingo",
        local_machine="flamingo",
        qdir=rs.queue_dir(install),
        install_root=install,
        home=home,
        machine_of_nick=bobreport.machine_from_nick,
        now=NOW,
    )
    args.update(kw)
    return rs.decide(**args)


def test_fr8602_parse_force_flag():
    assert rs.parse("!recycleseat flamingo-1 flamingo --force") == (
        "flamingo-1",
        "flamingo",
        True,
    )
    assert rs.parse("!recycleseat flamingo-1 --force") == ("flamingo-1", None, True)
    assert rs.parse("!recycleseat flamingo-1 flamingo") == ("flamingo-1", "flamingo", False)


def test_fr8602_fresh_busy_force_still_nacks(tmp_path, monkeypatch):
    install, home = setup_env(tmp_path, monkeypatch)
    bobreport.save_digest(
        home,
        {
            "machines": {
                "flamingo": {
                    "worker_list": [
                        {
                            "nick": SEAT,
                            "state": "doing",
                            "work": "MRB SimonBarnett/bobiverse#8549",
                            "updated": _iso_age(60),
                        }
                    ]
                }
            }
        },
    )
    d = ask(install, home, f"!recycleseat {SEAT} flamingo --force")
    assert not d.ok and d.reason == "busy"
    assert "stuck" in d.line.lower() or "force" in d.line.lower()
    assert not list(rs.queue_dir(install).glob("req-*.json"))


def test_fr8602_stale_updated_force_acks(tmp_path, monkeypatch):
    install, home = setup_env(tmp_path, monkeypatch)
    bobreport.save_digest(
        home,
        {
            "machines": {
                "flamingo": {
                    "worker_list": [
                        {
                            "nick": SEAT,
                            "state": "doing",
                            "work": "MRB SimonBarnett/bobiverse#8549",
                            "updated": _iso_age(2000),
                        }
                    ]
                }
            }
        },
    )
    d = ask(install, home, f"!recycleseat {SEAT} flamingo --force")
    assert d.ok, d.line
    assert list(rs.queue_dir(install).glob("req-*.json"))


def test_fr8602_accepted_silent_force_acks(tmp_path, monkeypatch):
    install, home = setup_env(tmp_path, monkeypatch)
    bobreport.save_digest(
        home,
        {
            "machines": {
                "flamingo": {
                    "worker_list": [
                        {
                            "nick": SEAT,
                            "state": "doing",
                            "work": "FR SimonBarnett/bobiverse#8578",
                            "updated": _iso_age(120),
                            "stuck_reason": "accepted_silent",
                        }
                    ]
                }
            }
        },
    )
    d = ask(install, home, f"!recycleseat {SEAT} flamingo --force")
    assert d.ok, d.line


def test_fr8602_stale_without_force_still_nacks_busy(tmp_path, monkeypatch):
    """Without --force, FR #5890 busy gate still protects even stale doing seats."""
    install, home = setup_env(tmp_path, monkeypatch)
    bobreport.save_digest(
        home,
        {
            "machines": {
                "flamingo": {
                    "worker_list": [
                        {
                            "nick": SEAT,
                            "state": "doing",
                            "work": "MRB #8549",
                            "updated": _iso_age(5000),
                        }
                    ]
                }
            }
        },
    )
    d = ask(install, home, f"!recycleseat {SEAT} flamingo")
    assert not d.ok and d.reason == "busy"
    assert "working_on" in d.line
