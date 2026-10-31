"""MRB #5445 hostile pins: AircConsoleService imports airc_extension before construct."""
from __future__ import annotations

from repo_layout import ROOT

import airc_console_service as svc


def test_mrb5445_import_before_extension_runner_kwarg():
    src = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert "import airc_extension as _airc_extension" in src
    assert src.index("import airc_extension as _airc_extension") < src.index(
        "extension_runner=_airc_extension.service_extension_runner"
    )
    assert callable(svc._airc_extension.service_extension_runner)
    assert not (ROOT / "airc" / "scripts" / "airc_console_service.py").read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb5445_construct_does_not_nameerror(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    try:
        s = svc.AircConsoleService(args)
    except NameError as e:
        raise AssertionError("AircConsoleService still NameErrors _airc_extension") from e
    assert s.core.extension_runner is svc._airc_extension.service_extension_runner
