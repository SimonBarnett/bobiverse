"""Hostile MRB #5081 / FR #5079: WinError pipe-close and launcher argv."""
from __future__ import annotations

import errno
import sys
from pathlib import Path

import airc_console_service as svc


def test_mrb5081_info_survives_winerror_232(tmp_path, monkeypatch):
    log = tmp_path / "side.log"
    svc.configure_log_file(log)

    class _Boom:
        encoding = "utf-8"

        def write(self, *_a, **_k):
            raise OSError(22, "Invalid argument")

        def flush(self):
            pass

    _Boom.write = lambda self, *_a, **_k: (_ for _ in ()).throw(
        OSError(22, "Invalid argument")
    )
    err = OSError(22, "Invalid argument")
    err.winerror = 232
    err.errno = errno.EINVAL

    class _WinBoom:
        encoding = "utf-8"

        def write(self, *_a, **_k):
            raise err

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stdout", _WinBoom())
    try:
        svc.info("INFO mrb5081-win232")
    finally:
        svc.configure_log_file(None)
    assert "mrb5081-win232" in log.read_text(encoding="utf-8")


def test_mrb5081_launcher_start_process_has_no_redirect():
    text = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "Start-AircConsoleSideBySide.ps1"
    ).read_text(encoding="utf-8")
    # The Start-Process invocation (not comments) must stay unpiped.
    invoke = text.split("# Detached:")[-1]
    assert "Start-Process" in invoke
    assert "-RedirectStandardOutput" not in invoke
    assert "-RedirectStandardError" not in invoke
    assert "--log-file" in text
