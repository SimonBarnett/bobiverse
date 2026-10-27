"""FR #5079: side-by-side --log-file tee + BrokenPipe-safe info()."""
from __future__ import annotations

import sys
from pathlib import Path

import airc_console_service as svc


def test_fr5079_configure_log_file_tees_info(tmp_path):
    log = tmp_path / "side.log"
    svc.configure_log_file(log)
    try:
        svc.info("INFO fr5079-unit-tee")
    finally:
        svc.configure_log_file(None)
    text = log.read_text(encoding="utf-8")
    assert "fr5079-unit-tee" in text
    assert "INFO fr5079-unit-tee" in text


def test_fr5079_info_survives_broken_stdout_pipe(tmp_path, monkeypatch):
    log = tmp_path / "side.log"
    svc.configure_log_file(log)

    class _Boom:
        encoding = "utf-8"

        def write(self, *_a, **_k):
            raise BrokenPipeError()

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stdout", _Boom())
    try:
        svc.info("INFO fr5079-broken-pipe")  # must not raise
    finally:
        svc.configure_log_file(None)
    assert "fr5079-broken-pipe" in log.read_text(encoding="utf-8")


def test_fr5079_argparse_log_file():
    p = svc.build_arg_parser()
    ns = p.parse_args(["--log-file", r"C:\tmp\airc-side.log", "--selftest"])
    assert ns.log_file == r"C:\tmp\airc-side.log"


def test_fr5079_side_by_side_launcher_script_exists():
    here = Path(__file__).resolve().parents[1] / "scripts" / "Start-AircConsoleSideBySide.ps1"
    assert here.is_file(), here
    text = here.read_text(encoding="utf-8")
    assert "--log-file" in text
    assert "RedirectStandardOutput" in text
    assert "FR #5079" in text
    # Must not redirect stdout/stderr on Start-Process for the long-lived host.
    assert "-RedirectStandardOutput" not in text.split("Start-Process")[-1]


def test_fr5079_pack_embeds_side_by_side_launcher():
    pack = Path(__file__).resolve().parents[1] / "scripts" / "Pack-AircConsoleRelease.ps1"
    text = pack.read_text(encoding="utf-8")
    assert "Start-AircConsoleSideBySide.ps1" in text
