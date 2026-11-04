"""Tests for OpenCode worker seat wiring (issue #6120)."""
from __future__ import annotations

from pathlib import Path

import pytest

import bob.scripts.bob_worker as bw


CUR, GRK, OP = r"C:\c\agent.cmd", r"C:\g\agent.exe", r"C:\o\opencode.exe"


def test_parse_fuel_reads_opencode_section():
    text = (
        '{"cursor":{"high":1,"low":2},'
        '"grok":{"remaining_pct":3,"state":"available"},'
        '"opencode":{"free":100,"go":50,"models":{"glm-5.3":50}}}'
    )
    f = bw.parse_fuel(text)
    assert f.cursor_high == 1
    assert f.grok_pct == 3
    assert f.opencode_free == 100
    assert f.opencode_go == 50
    assert f.opencode_models == {"glm-5.3": 50}


def test_opencode_has_tokens_unknown_is_not_available():
    assert bw.opencode_has_tokens(bw.Fuel()) is False
    assert bw.opencode_has_tokens(bw.Fuel(opencode_free=None, opencode_go=None)) is False
    assert bw.opencode_has_tokens(bw.Fuel(opencode_free=0, opencode_go=0)) is False
    assert bw.opencode_has_tokens(bw.Fuel(opencode_free=100, opencode_go=None)) is True
    assert bw.opencode_has_tokens(bw.Fuel(opencode_free=None, opencode_go=42)) is True


def test_fuel_reading_known_and_exhausted_for_opencode():
    available = bw.Fuel(opencode_free=100, opencode_go=50)
    assert bw.fuel_reading_known(available, "opencode") is True
    assert bw.fuel_explicitly_exhausted(available, "opencode") is False
    exhausted = bw.Fuel(opencode_free=0, opencode_go=0)
    assert bw.fuel_explicitly_exhausted(exhausted, "opencode") is True
    unknown = bw.Fuel()
    assert bw.fuel_reading_known(unknown, "opencode") is False
    assert bw.fuel_explicitly_exhausted(unknown, "opencode") is False


def test_select_agent_prefers_grok_then_cursor_then_opencode():
    assert bw.select_agent(bw.Fuel(5, 5, 50, "available"), CUR, GRK, OP).kind == "grok"
    assert bw.select_agent(bw.Fuel(5, 5, 0, "exhausted"), CUR, GRK, OP).kind == "cursor"
    assert bw.select_agent(bw.Fuel(0, 0, 0, "exhausted", opencode_go=50), CUR, GRK, OP).kind == "opencode"
    assert bw.select_agent(bw.Fuel(0, 0, 0, "exhausted", opencode_go=50), CUR, GRK, None).kind == "dialog"


def test_select_agent_opencode_only():
    fuel = bw.Fuel(opencode_free=100, opencode_go=50)
    assert bw.select_agent(fuel, None, None, OP).kind == "opencode"
    assert bw.select_agent(fuel, None, None, None).kind == "none"


def test_opencode_default_model():
    assert bw.opencode_default_model(bw.Fuel(opencode_go=50)) == "opencode-go/glm-5.3"
    assert bw.opencode_default_model(bw.Fuel(opencode_go=0, opencode_free=100)) == "opencode-free/beam-free"
    assert bw.opencode_default_model(bw.Fuel()) is None


def test_opencode_default_model_skips_exhausted_glm53():
    """Per-model fuel must be respected: glm-5.3 at 0 should not be chosen."""
    fuel = bw.Fuel(
        opencode_go=50,
        opencode_models={"glm-5.3": 0, "kimi-k3": 50},
    )
    selected = bw.opencode_default_model(fuel)
    assert selected != "opencode-go/glm-5.3"
    assert selected == "opencode-go/kimi-k3"


def test_build_launch_opencode_creates_wrapper(tmp_path: Path):
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "Do work.", OP, tmp_path)
    assert spec.argv[0] == "powershell.exe"
    assert "launch-opencode.ps1" in spec.argv[-1]
    prompt_key = next(k for k in spec.files if k.endswith("prompt.txt"))
    script_key = next(k for k in spec.files if k.endswith("launch-opencode.ps1"))
    script = spec.files[script_key]
    assert "opencode.exe" in script or OP in script
    assert "run -m $model" in script
    assert "Do work." in spec.files[prompt_key]


def test_should_start_fuel_watcher_includes_opencode():
    assert bw.should_start_fuel_watcher("opencode") is True
    assert bw.should_start_fuel_watcher("plan") is False


def test_read_fuel_parses_opencode_section(tmp_path: Path):
    (tmp_path / "tools").mkdir()
    payload = (
        '{"ok":true,"cursor":{"high":5,"low":0},'
        '"grok":{"remaining_pct":null,"state":"unknown"},'
        '"opencode":{"free":100,"go":50,"models":{"glm-5.3":50}}}'
    )
    (tmp_path / "tools" / "Get-BobAgentFuel.ps1").write_text(
        f"[Console]::Out.WriteLine('{payload}')\nexit 0",
        encoding="utf-8",
    )

    class R:
        stdout = payload

    def run(argv, **k):
        return R()

    f = bw.read_fuel(tmp_path, run)
    assert f.opencode_free == 100
    assert f.opencode_go == 50
    assert f.opencode_models == {"glm-5.3": 50}


OPENCODE_FUEL_PS1 = Path(bw.__file__).resolve().parent.parent / "tray" / "tools" / "Get-BobOpencodeFuel.ps1"


def test_opencode_fuel_ps1_uses_models_plain_text_stats():
    text = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "stats --models" in text
    assert "stats --json" not in text
    assert "--output json" not in text


def test_opencode_fuel_ps1_pipes_text_via_stdin():
    text = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "$statsRaw | & $py -c $script" in text
    assert "sys.stdin.read()" in text
    assert "sys.argv[1]" not in text


def test_opencode_fuel_ps1_pythonpath_points_to_repo_common_scripts():
    text = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))" in text
    assert "common\\scripts" in text


def test_opencode_fuel_ps1_uses_opencode_fuel_translation():
    text = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "opencode_fuel" in text
    assert "parse_opencode_stats_text_or_json" in text
    assert "fuel_from_stats" in text
