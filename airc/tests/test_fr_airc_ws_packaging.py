"""FR #7999: ship the WebSocket transport in every Airc artefact path."""
from __future__ import annotations

from pathlib import Path

import airc_console_service as svc
from airc_ci_source_paths import airc_ci_source_paths
from repo_layout import ROOT


def test_service_imports_ws_transport_as_alias():
    assert hasattr(svc, "_ws")
    assert hasattr(svc._ws, "connect_ws")
    assert hasattr(svc._ws, "safe_label")
    assert hasattr(svc._ws, "validate_url")


def test_client_allowlist_includes_ws_transport():
    text = (ROOT / "common" / "scripts" / "Bobiverse-Common.ps1").read_text(encoding="utf-8")
    assert "'airc_ws_transport.py'" in text


def test_pack_source_list_includes_ws_transport():
    text = (ROOT / "airc" / "scripts" / "Pack-AircConsoleRelease.ps1").read_text(encoding="utf-8")
    assert "airc_ws_transport.py" in text


def test_ci_path_filter_covers_airc_glob():
    paths = airc_ci_source_paths()
    assert "airc/**" in paths


def test_ws_transport_module_no_bom_and_stdlib_only():
    path = ROOT / "airc" / "scripts" / "airc_ws_transport.py"
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    text = path.read_text(encoding="utf-8")
    for forbidden in ("import websocket", "import requests", "import aiohttp", "import websockets"):
        assert forbidden not in text, f"non-stdlib import {forbidden!r}"
    assert "FR #7999" in text


def test_ws_transport_constructs_without_connection():
    # Import-and-construct guard (mirrors test_fr5426): no socket, just the class.
    from airc_ws_transport import WebSocketError, WebSocketHandshakeError, WebSocketTransport

    assert issubclass(WebSocketHandshakeError, WebSocketError)
    assert issubclass(WebSocketError, OSError)
    assert callable(WebSocketTransport.sendall)
