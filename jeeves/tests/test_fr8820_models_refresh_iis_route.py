"""FR #8820: BobModelsWebhook rewrite reaches POST /bob/v1/models/refresh."""
from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from repo_layout import REPO

SCRIPT = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")


def _run_install(physical: Path, *, backend: str = "http://127.0.0.1:7700") -> subprocess.CompletedProcess:
    args = [
        PS,
        "-NoProfile",
        "-File",
        str(SCRIPT),
        "-PhysicalPath",
        str(physical),
        "-Backend",
        backend,
    ]
    return subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)


def _parse_models_rule(web_config: Path) -> tuple[str, str]:
    text = web_config.read_text(encoding="utf-8")
    block_re = re.compile(
        r'<rule\s+name="BobModelsWebhook"[^>]*>.*?</rule>',
        re.IGNORECASE | re.DOTALL,
    )
    m = block_re.search(text)
    assert m, "BobModelsWebhook rule missing"
    block = m.group(0)
    match_m = re.search(r'<match\s+url="([^"]+)"', block, re.IGNORECASE)
    action_m = re.search(r'<action\s+[^>]*url="([^"]+)"', block, re.IGNORECASE)
    assert match_m and action_m
    return match_m.group(1), action_m.group(1)


def _expand_rewrite(match_pat: str, action_url: str, path: str) -> str:
    cre = re.compile(match_pat, re.IGNORECASE)
    m = cre.match(path)
    assert m, f"{path!r} did not match {match_pat!r}"
    out = action_url
    for i, g in enumerate(m.groups(), start=1):
        out = out.replace(f"{{R:{i}}}", g if g is not None else "")
    return out


@NEED_PS
def test_sitekit_models_rule_forwards_refresh(tmp_path: Path):
    site = tmp_path / "irc-ntsa"
    site.mkdir()
    r1 = _run_install(site)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    cfg = site / "web.config"
    assert cfg.is_file()
    match_pat, action_url = _parse_models_rule(cfg)
    target = _expand_rewrite(match_pat, action_url, "bob/v1/models/refresh")
    assert target == "http://127.0.0.1:7700/bob/v1/models/refresh"
    # FR #9224: method filter must admit POST (PUT/PATCH stay out).
    block = cfg.read_text(encoding="utf-8")
    models_block = re.search(
        r'<rule\s+name="BobModelsWebhook"[^>]*>.*?</rule>',
        block,
        re.IGNORECASE | re.DOTALL,
    )
    assert models_block and "GET|HEAD|POST" in models_block.group(0)

    # Upgrade path: existing config without models rule, then re-install.
    body = cfg.read_text(encoding="utf-8")
    stripped = re.sub(
        r'\s*<rule\s+name="BobModelsWebhook"[^>]*>.*?</rule>',
        "",
        body,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cfg.write_text(stripped, encoding="utf-8")
    assert "BobModelsWebhook" not in cfg.read_text(encoding="utf-8")
    r2 = _run_install(site)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    match_pat2, action_url2 = _parse_models_rule(cfg)
    target2 = _expand_rewrite(match_pat2, action_url2, "bob/v1/models/refresh")
    assert target2.endswith("/bob/v1/models/refresh")


@NEED_PS
def test_loopback_post_refresh_via_expanded_path(tmp_path: Path):
    sys.path.insert(0, str(REPO / "common" / "scripts"))
    import models_catalog as mc
    import models_refresh as mr
    from bobcallback import make_handler

    home = tmp_path / "digest"
    home.mkdir()
    (home / mc.MODELS_CATALOG_NAME).write_text(
        json.dumps({"version": 1, "agents": mc.default_agent_rows(), "clis": {}}),
        encoding="utf-8",
    )
    clock = {"t": 5000.0}

    def now() -> float:
        return clock["t"]

    ctl = mr.ModelsRefreshController(
        home,
        listers={
            "grok": lambda: ["g-loop"],
            "cursor": lambda: ["c-loop"],
            "opencode": lambda: ["opencode/loop"],
        },
        clock=now,
    )
    handler = make_handler(
        home,
        allow_ips={"127.0.0.1"},
        models_refresh_ctl=ctl,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        path = "/bob/v1/models/refresh"
        body = b""
        req = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii") + body
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(req)
            raw = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                raw += chunk
        assert b"200" in raw.split(b"\r\n", 1)[0]
        assert b'"clis"' in raw
    finally:
        httpd.shutdown()
