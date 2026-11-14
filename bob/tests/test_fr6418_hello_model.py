"""FR #6418: worker hello line reports the configured model (kind= model= build=)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw  # noqa: E402


def test_fr6418_hello_line_field_order_kind_model_build():
    line = bw.worker_hello_line("opencode", model="opencode-go/glm-5.3", build="abc123def456")
    assert line == "worker ready kind=opencode model=opencode-go/glm-5.3 build=abc123def456"


def test_fr6418_hello_line_reads_opencode_config_model(tmp_path, monkeypatch):
    cfg = tmp_path / "opencode.jsonc"
    cfg.write_text('// glm trial\n{ "model": "opencode-go/glm-5.3" }\n', encoding="utf-8")
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    line = bw.worker_hello_line("opencode", build="abc123def456")
    # FR #7187: machine Go/paid OpenCode config is skipped; hello reports free Flash.
    assert line == "worker ready kind=opencode model=opencode/deepseek-v4.1-flash-free build=abc123def456"


def test_fr6418_env_launch_model_wins_over_config(tmp_path, monkeypatch):
    cfg = tmp_path / "opencode.json"
    cfg.write_text('{"model": "opencode/beam-free"}', encoding="utf-8")
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    monkeypatch.setenv("BOB_OPENCODE_MODEL", "opencode-go/glm-5.3")
    line = bw.worker_hello_line("opencode", build="abc123def456")
    assert line == "worker ready kind=opencode model=opencode-go/glm-5.3 build=abc123def456"


def test_fr6418_unreadable_config_gives_unknown(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    monkeypatch.setenv("OPENCODE_CONFIG", str(tmp_path / "absent.jsonc"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    line = bw.worker_hello_line("opencode", build="abc123def456")
    assert line == "worker ready kind=opencode model=opencode/deepseek-v4.1-flash-free build=abc123def456"


def test_fr6418_non_utf8_config_skipped_not_raised(tmp_path, monkeypatch):
    cfg = tmp_path / "opencode.jsonc"
    cfg.write_bytes(b'{\xff\xfe "model": "opencode-go/glm-5.3" }')
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert bw.read_opencode_config_model() is None
    line = bw.worker_hello_line("opencode", build="abc123def456")
    assert "model=opencode/deepseek-v4.1-flash-free" in line


def test_fr6418_malformed_config_gives_unknown(tmp_path, monkeypatch):
    cfg = tmp_path / "opencode.jsonc"
    cfg.write_text("{ not json at all", encoding="utf-8")
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    line = bw.worker_hello_line("opencode", build="abc123def456")
    assert "model=opencode/deepseek-v4.1-flash-free" in line


def test_fr6418_other_kinds_report_unknown_never_omit():
    for kind in ("grok", "cursor", "aider", ""):
        line = bw.worker_hello_line(kind, build="abc123def456")
        assert line.endswith(" model=unknown build=abc123def456"), kind
        assert "model=" in line


def test_fr6418_resolve_seat_hello_model_empty_for_non_opencode():
    assert bw.resolve_seat_hello_model("grok") == ""
    assert bw.resolve_seat_hello_model("cursor") == ""


def test_fr6418_digest_carries_same_model(monkeypatch):
    captured: dict[str, Any] = {}

    def _fake_post(url: str, payload: dict, log=None):
        captured["payload"] = dict(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", _fake_post)
    ok = bw.post_digest_seat_kind(
        machine="marchhare",
        pid=42,
        nick="marchhare-42",
        kind="opencode",
        model="opencode-go/glm-5.3",
        worker_build="abc123def456",
        url="https://example.test/bob/v1/report",
    )
    assert ok is True
    assert captured["payload"]["model"] == "opencode-go/glm-5.3"
    assert captured["payload"]["worker_build"] == "abc123def456"


def test_fr6418_run_agent_shares_one_model_value():
    """Hostile pin: digest payload and hello line must use the same seat_model value."""
    src = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    chunk = src[src.find("def run_agent("):]
    assert "seat_model = resolve_seat_hello_model(kind)" in chunk
    assert "model=seat_model" in chunk  # post_digest_seat_kind payload
    assert "worker_hello_line(kind," in chunk
    assert "hello_model" in chunk or "model=seat_model" in chunk


def test_fr7084_grok_build_launch_inserts_configured_model(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "BOB_WORKER_START_MODEL_JSON",
        json.dumps({"workerStartModels": {"grok": "EXAMPLE_GROK_MIN"}}),
    )
    rd = tmp_path / "run"
    rd.mkdir()
    spec = bw.build_launch(
        "grok",
        "agent",
        str(tmp_path / "cwd"),
        "prompt",
        r"C:\fake\grok.exe",
        rd,
        session_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    assert "--model" in spec.argv
    assert spec.argv[spec.argv.index("--model") + 1] == "EXAMPLE_GROK_MIN"


def test_fr7084_resolve_seat_hello_uses_worker_start_models(monkeypatch):
    monkeypatch.setenv(
        "BOB_WORKER_START_MODEL_JSON",
        json.dumps({"workerStartModels": {"cursor": "EXAMPLE_CURSOR_MIN"}}),
    )
    assert bw.resolve_seat_hello_model("cursor") == "EXAMPLE_CURSOR_MIN"


def test_fr6418_docs_mention_hello_model():
    text = (ROOT / "bob" / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "model=<configured model>" in text
    assert "model=unknown" in text or "`unknown`" in text
