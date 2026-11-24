# -*- coding: utf-8 -*-
"""FR #9861: OS named mutex refuses same-home+nick twin bob-ear (NSSM same-second)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import irc_agent as ear
import pytest


@pytest.fixture(autouse=True)
def _release_mutex():
    yield
    ear.release_ear_instance_mutex()


def test_ear_mutex_name_stable_per_home_nick(tmp_path: Path):
    a = ear.ear_instance_mutex_name(tmp_path, "Bob-redqueen")
    b = ear.ear_instance_mutex_name(tmp_path, "Bob-redqueen")
    c = ear.ear_instance_mutex_name(tmp_path, "Bob-other")
    assert a == b
    assert a.startswith("Global\\BobiverseBobEar-")
    assert a != c


def test_second_acquire_same_name_refuses_on_windows(tmp_path: Path):
    if os.name != "nt":
        pytest.skip("named mutex is Windows-only")
    assert ear.try_acquire_ear_instance_mutex(tmp_path, "Bob-redqueen") is True
    # Same process CreateMutexW on existing name -> ERROR_ALREADY_EXISTS
    assert ear.try_acquire_ear_instance_mutex(tmp_path, "Bob-redqueen") is False
    ear.release_ear_instance_mutex()
    assert ear.try_acquire_ear_instance_mutex(tmp_path, "Bob-redqueen") is True


def test_empty_home_or_nick_fail_open(tmp_path: Path):
    assert ear.try_acquire_ear_instance_mutex("", "Bob-x") is True
    assert ear.try_acquire_ear_instance_mutex(tmp_path, "") is True


def test_main_exits_3_when_mutex_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        ear,
        "try_acquire_ear_instance_mutex",
        lambda home, nick: False,
    )
    monkeypatch.setattr(ear, "assert_ear_dispatch_contracts", lambda: None)
    monkeypatch.setattr(
        ear.sys,
        "argv",
        [
            "irc_agent",
            "--nick",
            "Bob-flamingo",
            "--channel",
            "#flamingo",
            "--home",
            str(tmp_path),
            "--host",
            "127.0.0.1",
            "--port",
            "6697",
        ],
    )
    # Avoid real prior-clean / Client if mutex somehow passed
    monkeypatch.setattr(ear, "clean_crashed_priors", lambda *a, **k: None)

    class _Boom:
        def __init__(self, *_a, **_k):
            raise AssertionError("Client must not start when mutex busy")

    monkeypatch.setattr(ear, "Client", _Boom)
    with pytest.raises(SystemExit) as ei:
        ear.main()
    assert ei.value.code == ear._EAR_MUTEX_EXIT


def test_once_skips_mutex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    called = {"n": 0}

    def _acq(*_a, **_k):
        called["n"] += 1
        return False

    monkeypatch.setattr(ear, "try_acquire_ear_instance_mutex", _acq)
    monkeypatch.setattr(ear, "assert_ear_dispatch_contracts", lambda: None)
    monkeypatch.setattr(ear, "clean_crashed_priors", lambda *a, **k: None)

    class _Client:
        def __init__(self, *_a, **_k):
            pass

        def session(self):
            return None

        def run_forever(self):
            return None

        def request_shutdown(self, *_a):
            return None

    monkeypatch.setattr(ear, "Client", _Client)
    monkeypatch.setattr(
        ear.sys,
        "argv",
        [
            "irc_agent",
            "--nick",
            "Bob-flamingo",
            "--channel",
            "#flamingo",
            "--home",
            str(tmp_path),
            "--once",
            "--host",
            "127.0.0.1",
            "--port",
            "6697",
        ],
    )
    ear.main()
    assert called["n"] == 0
