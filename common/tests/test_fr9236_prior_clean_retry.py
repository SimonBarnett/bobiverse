"""FR #9236: prior-clean scan retries so the first restart after a self-exit can connect.

Transient CIM / PowerShell failures must not abort connect on the first attempt.
Persistent failures stay fail-closed (scanned=False). No machine names.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import prior_irc


def test_fr9236_scan_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("BOB_PRIOR_SCAN_ATTEMPTS", "3")
    monkeypatch.setenv("BOB_PRIOR_SCAN_BACKOFF_S", "0")
    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd="ps", timeout=30)
        return []

    result = prior_irc.clean_priors(
        "bob-test",
        str(Path.home() / ".bobiverse-fr9236"),
        wait_s=0,
        list_processes=flaky,
        sleeper=lambda s: sleeps.append(float(s)),
    )
    assert result.scanned is True
    assert calls["n"] == 2
    assert result.scan_attempts >= 2


def test_fr9236_persistent_scan_failure_fail_closed(monkeypatch):
    monkeypatch.setenv("BOB_PRIOR_SCAN_ATTEMPTS", "3")
    monkeypatch.setenv("BOB_PRIOR_SCAN_BACKOFF_S", "0")
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise OSError("cim unavailable")

    result = prior_irc.clean_priors(
        "bob-test",
        str(Path.home() / ".bobiverse-fr9236"),
        wait_s=0,
        list_processes=always_fail,
        sleeper=lambda _s: None,
    )
    assert result.scanned is False
    assert calls["n"] == 3
    assert result.scan_attempts == 3


def test_fr9236_oserror_then_prior_then_empty(monkeypatch):
    monkeypatch.setenv("BOB_PRIOR_SCAN_ATTEMPTS", "3")
    monkeypatch.setenv("BOB_PRIOR_SCAN_BACKOFF_S", "0")
    home = str(Path.home() / ".bobiverse-fr9236-kill")
    seq = [
        OSError("transient"),
        [(4242, f"python irc_agent.py --nick bob-test --home {home}")],
        [],
    ]
    calls = {"n": 0}
    killed: list[int] = []

    def lister():
        calls["n"] += 1
        item = seq.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    result = prior_irc.clean_priors(
        "bob-test",
        home,
        wait_s=0,
        list_processes=lister,
        killer=lambda pid: killed.append(pid) or True,
        sleeper=lambda _s: None,
    )
    assert result.scanned is True
    assert killed == [4242]
    assert calls["n"] == 3


def test_fr9236_parsing_error_propagates(monkeypatch):
    monkeypatch.setenv("BOB_PRIOR_SCAN_ATTEMPTS", "3")

    def bad():
        raise TypeError("not a scan transport error")

    try:
        prior_irc.clean_priors(
            "bob-test",
            str(Path.home() / ".bobiverse-fr9236"),
            wait_s=0,
            list_processes=bad,
            sleeper=lambda _s: None,
        )
        raise AssertionError("TypeError should propagate")
    except TypeError:
        pass


def test_fr9236_clean_crashed_priors_recovers_after_one_fail(monkeypatch):
    """Caller must not SystemExit when the first scan fails and a retry succeeds."""
    import irc_agent

    monkeypatch.delenv("BOB_IRC_SKIP_PRIOR_CLEAN", raising=False)
    monkeypatch.setenv("BOB_PRIOR_SCAN_ATTEMPTS", "3")
    monkeypatch.setenv("BOB_PRIOR_SCAN_BACKOFF_S", "0")
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("cim blip")
        return []

    real_clean = prior_irc.clean_priors

    def clean_with_flaky(*args, **kwargs):
        kwargs["list_processes"] = flaky
        kwargs["sleeper"] = lambda _s: None
        kwargs["wait_s"] = 0
        return real_clean(*args, **kwargs)

    # clean_crashed_priors does `import prior_irc` then calls prior_irc.clean_priors.
    monkeypatch.setattr(prior_irc, "clean_priors", clean_with_flaky)
    import sys

    sys.modules["prior_irc"] = prior_irc
    irc_agent.clean_crashed_priors("bob-test", str(Path.home() / ".bobiverse"), once=False)
    assert calls["n"] >= 2


def test_fr9236_persistent_scan_still_scanned_false_at_clean_priors(monkeypatch):
    """FR #9236 clean_priors stays fail-closed (scanned=False); FR #9496 opens connect."""
    monkeypatch.setenv("BOB_PRIOR_SCAN_ATTEMPTS", "2")
    monkeypatch.setenv("BOB_PRIOR_SCAN_BACKOFF_S", "0")

    def always_fail():
        raise OSError("cim unavailable")

    result = prior_irc.clean_priors(
        "bob-test",
        str(Path.home() / ".bobiverse-fr9236"),
        wait_s=0,
        list_processes=always_fail,
        sleeper=lambda _s: None,
    )
    assert result.scanned is False


def test_fr9236_source_has_no_machine_names():
    root = Path(__file__).resolve().parents[2]
    src = (root / "common" / "scripts" / "prior_irc.py").read_text(encoding="utf-8")
    assert "BOB_PRIOR_SCAN_ATTEMPTS" in src
    assert "FR #9236" in src or "scan-recovered" in src
    # Ban machine names only in the FR #9236 helpers (pre-existing module docstring may cite hosts).
    start = src.index("PRIOR_SCAN_ATTEMPTS_ENV")
    end = src.index("\ndef kill_pid", start)
    chunk = src[start:end].lower()
    banned = ("wal" + "rus", "red" + "queen", "flam" + "ingo")
    for name in banned:
        assert name not in chunk
    self_src = Path(__file__).read_text(encoding="utf-8").lower()
    for name in banned:
        assert name not in self_src
