"""FR #6774: bored-latency recycle window then hold + one stall report."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import stall_filer


def _prep(tmp_path, monkeypatch, machines):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, set(machines))
    digest = bobreport.empty_digest()
    for mid in machines:
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["worker_list"] = [
            {"nick": f"{mid}-1", "state": "idle"}
        ]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    return install


def _heal(tmp_path, install, nick, now, last_bored_lag=500.0, **kw):
    return gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - last_bored_lag},
        last_activity={},
        accepted=[],
        now=now,
        install_root=install,
        cooldown_s=0.0,
        **kw,
    )


def test_three_lags_two_recycles_one_hold(tmp_path, monkeypatch):
    install = _prep(tmp_path, monkeypatch, ["flamingo"])
    reports = []

    def capture(findings, **kwargs):
        reports.append(list(findings))
        return [{"fp": "x", "action": "created"}]

    monkeypatch.setattr(stall_filer, "apply_findings", capture)
    now = 1_700_000.0
    a = _heal(tmp_path, install, "flamingo-100", now)
    b = _heal(tmp_path, install, "flamingo-200", now + 10)
    c = _heal(tmp_path, install, "flamingo-300", now + 20)
    rec = [ln for ln in (a + b + c) if "recycleseat=" in ln]
    held = [ln for ln in (a + b + c) if "reason=recycle-loop" in ln]
    assert len(rec) == 2, (a, b, c)
    assert len(held) == 1, (a, b, c)
    assert len(reports) == 1
    outbox = tmp_path / "chair-outbox.txt"
    if not outbox.is_file():
        outbox = Path(bobreport.fleet_digest_home(tmp_path)) / "chair-outbox.txt"
    text = outbox.read_text(encoding="utf-8") if outbox.is_file() else ""
    assert text.count("!recycleseat") == 2, text
    assert "flamingo-300" not in text


def test_on_time_bored_clears_hold(tmp_path, monkeypatch):
    install = _prep(tmp_path, monkeypatch, ["flamingo"])
    monkeypatch.setattr(stall_filer, "apply_findings", lambda *a, **k: [])
    now = 1_700_000.0
    _heal(tmp_path, install, "flamingo-100", now)
    _heal(tmp_path, install, "flamingo-200", now + 10)
    _heal(tmp_path, install, "flamingo-300", now + 20)
    # on-time !bored on the new seat
    later = now + 40
    gitclaim.heal_bored_latency(
        tmp_path,
        idle={"flamingo-400"},
        last_bored={"flamingo-400": later - 10},
        last_activity={},
        accepted=[],
        now=later,
        install_root=install,
        cooldown_s=0.0,
    )
    again = _heal(tmp_path, install, "flamingo-400", later + 5)
    assert any("recycleseat=" in x for x in again), again


def test_other_machine_unaffected(tmp_path, monkeypatch):
    install = _prep(tmp_path, monkeypatch, ["flamingo", "redqueen"])
    monkeypatch.setattr(stall_filer, "apply_findings", lambda *a, **k: [])
    now = 1_700_000.0
    _heal(tmp_path, install, "flamingo-100", now)
    _heal(tmp_path, install, "flamingo-200", now + 10)
    _heal(tmp_path, install, "flamingo-300", now + 20)
    rq = _heal(tmp_path, install, "redqueen-9", now + 30)
    assert any("recycleseat=redqueen-9" in x for x in rq), rq


def test_resync_clears_hold():
    src = (
        Path(__file__).resolve().parents[2]
        / "common"
        / "scripts"
        / "chair_health.py"
    ).read_text(encoding="utf-8")
    fn = src[src.find("def request_resync") :]
    assert "clear_bored_latency_recycle_holds" in fn[:600]
