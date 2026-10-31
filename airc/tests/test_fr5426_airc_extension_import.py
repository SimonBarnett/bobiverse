"""FR #5426: AircConsoleService must bind airc_extension before extension_runner=."""
from __future__ import annotations

import airc_console_service as svc
from repo_layout import ROOT


def test_fr5426_airc_extension_imported_as_alias():
    assert hasattr(svc, "_airc_extension")
    assert hasattr(svc._airc_extension, "service_extension_runner")
    src = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert "import airc_extension as _airc_extension" in src or "import airc_extension as _airc_extension" in src.replace(
        "\r\n", "\n"
    )
    assert "FR #5426" in src or "airc_extension as _airc_extension" in src
    assert not (ROOT / "airc" / "scripts" / "airc_console_service.py").read_bytes().startswith(b"\xef\xbb\xbf")


def test_fr5426_console_service_constructs_with_extension_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "x-server-pass")
    args = svc.build_arg_parser().parse_args(
        ["--machine", "tm", "--home", str(tmp_path), "--shop-mode", "registered", "--operators", "op"]
    )
    s = svc.AircConsoleService(args)
    assert s.core is not None
    assert getattr(s.core, "extension_runner", None) is svc._airc_extension.service_extension_runner
