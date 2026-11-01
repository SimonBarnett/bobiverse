"""FR #5756: non-target ears stay silent before authorize; Jeeves without account."""
from __future__ import annotations

import recycleseat as rs


MID = lambda n: "marchhare" if str(n).lower().startswith("bob-marchhare") else None  # noqa: E731


def _decide(**kw):
    defaults = dict(
        body="!recycleseat flamingo-72904 flamingo",
        nick="Jeeves",
        account=None,
        channel="#bobiverse",
        local_machine="marchhare",
        qdir="/tmp/unused",
        install_root="/tmp/unused",
        machine_of_nick=MID,
        member_lookup=lambda ch, n: set(),
        write=False,
    )
    defaults.update(kw)
    return rs.decide(**defaults)


def test_fr5756_non_target_silent_even_when_unverified():
    """Auth must not run first — unverified Jeeves on wrong machine stays silent."""
    d = _decide(
        body="!recycleseat flamingo-72904 flamingo",
        nick="Jeeves",
        account=None,
        channel="#bobiverse",
        local_machine="marchhare",
    )
    assert d is None


def test_fr5756_target_shop_jeeves_without_account_acks(tmp_path):
    import os

    import startworker as sw

    install = tmp_path / "install"
    q = install / "run" / "recycleseat"
    q.mkdir(parents=True)
    adir = sw.queue_dir(install)
    adir.mkdir(parents=True, exist_ok=True)
    now = 1_700_000.0
    for name in ("tray.alive", "engine.alive"):
        path = adir / name
        path.write_text("1", encoding="utf-8")
        os.utime(path, (now, now))
    d = rs.decide(
        body="!recycleseat flamingo-72904 flamingo",
        nick="Jeeves",
        account=None,
        channel="#flamingo",
        local_machine="flamingo",
        qdir=q,
        install_root=install,
        machine_of_nick=MID,
        member_lookup=lambda ch, n: set(),
        now=now,
        write=True,
    )
    assert d is not None
    assert d.ok, (d.reason, d.line)
    assert d.kind == "chair"
    assert "ACK recycleseat flamingo-72904" in d.line


def test_fr5756_authorize_jeeves_no_account():
    ok, kind, why = rs.authorize(
        "Jeeves",
        None,
        channel="#flamingo",
        machine_of_nick=MID,
        member_lookup=lambda ch, n: set(),
    )
    assert ok and kind == "chair" and why == ""


def test_fr5756_authorize_op_without_account():
    ok, kind, why = rs.authorize(
        "Simon",
        None,
        channel="#flamingo",
        machine_of_nick=MID,
        member_lookup=lambda ch, n: {"o"} if n.lower() == "simon" else set(),
    )
    assert ok and kind == "op"
