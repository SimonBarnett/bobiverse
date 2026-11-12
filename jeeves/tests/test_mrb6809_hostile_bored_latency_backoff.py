"""Hostile pins for MRB #6809 / FR #6774 bored-latency recycle backoff."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import stall_filer


def _prep(tmp_path, monkeypatch, machines=("flamingo",)):
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


def _heal(tmp_path, install, nick, now, last_bored_lag=500.0):
    return gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: now - last_bored_lag},
        last_activity={},
        accepted=[],
        now=now,
        install_root=install,
        cooldown_s=0.0,
    )


def test_mrb6809_held_slot_no_second_report_or_recycle(tmp_path, monkeypatch):
    """While held, further lagging heals must not recycle or re-file intake."""
    install = _prep(tmp_path, monkeypatch)
    reports = []

    def capture(findings, **kwargs):
        reports.append(list(findings))
        return [{"fp": "x", "action": "created"}]

    monkeypatch.setattr(stall_filer, "apply_findings", capture)
    now = 1_700_000.0
    _heal(tmp_path, install, "flamingo-100", now)
    _heal(tmp_path, install, "flamingo-200", now + 10)
    held = _heal(tmp_path, install, "flamingo-300", now + 20)
    assert any("reason=recycle-loop" in x for x in held)
    assert len(reports) == 1
    again = _heal(tmp_path, install, "flamingo-400", now + 30)
    assert not any("recycleseat=" in x for x in again), again
    assert any("reason=recycle-loop" in x for x in again), again
    assert len(reports) == 1


def test_mrb6809_hold_survives_recycle_window_prune(tmp_path, monkeypatch):
    """Rolling window pruning stamps must not silently resume recycles while held."""
    install = _prep(tmp_path, monkeypatch)
    monkeypatch.setattr(stall_filer, "apply_findings", lambda *a, **k: [])
    now = 1_700_000.0
    _heal(tmp_path, install, "flamingo-100", now)
    _heal(tmp_path, install, "flamingo-200", now + 10)
    _heal(tmp_path, install, "flamingo-300", now + 20)
    later = now + float(gitclaim.BORED_LATENCY_RECYCLE_WINDOW_S) + 120.0
    out = _heal(tmp_path, install, "flamingo-500", later)
    assert not any("recycleseat=" in x for x in out), out
    assert any("reason=recycle-loop" in x for x in out), out


def test_mrb6809_clear_holds_helper_allows_recycle(tmp_path, monkeypatch):
    """Operator clear (as !resync) drops hold + stamps so recycle is allowed again."""
    install = _prep(tmp_path, monkeypatch)
    monkeypatch.setattr(stall_filer, "apply_findings", lambda *a, **k: [])
    now = 1_700_000.0
    _heal(tmp_path, install, "flamingo-100", now)
    _heal(tmp_path, install, "flamingo-200", now + 10)
    _heal(tmp_path, install, "flamingo-300", now + 20)
    gitclaim.clear_bored_latency_recycle_holds(tmp_path)
    again = _heal(tmp_path, install, "flamingo-600", now + 40)
    assert any("recycleseat=flamingo-600" in x for x in again), again
