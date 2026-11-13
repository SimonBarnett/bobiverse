"""FR #6986: Jeeves logs when a stall-heal recycle left the same nick lagging."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import stall_filer


def _prep(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"redqueen"})
    digest = bobreport.empty_digest()
    digest["machines"]["redqueen"] = bobreport._empty_machine("redqueen")
    digest["machines"]["redqueen"]["worker_list"] = [
        {"nick": "redqueen-7376", "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    install = tmp_path / "install"
    install.mkdir()
    monkeypatch.setattr(stall_filer, "apply_findings", lambda *a, **k: [])
    return install


def test_same_nick_second_heal_logs_recycle_no_effect(tmp_path, monkeypatch):
    install = _prep(tmp_path, monkeypatch)
    nick = "redqueen-7376"
    t0 = 1_700_000.0
    first = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: t0 - 342},
        last_activity={},
        accepted=[],
        now=t0,
        install_root=install,
        cooldown_s=0.0,
    )
    assert any("recycleseat=redqueen-7376" in x for x in first), first
    assert not any("recycle-no-effect" in x for x in first), first
    second = gitclaim.heal_bored_latency(
        tmp_path,
        idle={nick},
        last_bored={nick: t0 - 342},
        last_activity={},
        accepted=[],
        now=t0 + 900,
        install_root=install,
        cooldown_s=0.0,
    )
    nofx = [x for x in second if "recycle-no-effect" in x]
    assert nofx, second
    assert "seat=redqueen-7376" in nofx[0]
    assert "attempts=" in nofx[0]
