"""Tests for OpenCode worker seat wiring (issue #6120)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
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
    assert bw.opencode_default_model(
        bw.Fuel(opencode_go=0, opencode_free=100, opencode_free_model_ids=("opencode/beam-free",))
    ) == "opencode/beam-free"
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


def test_opencode_default_model_prefers_free_when_no_per_model_readings():
    """Without per-model readings, free fuel should be chosen over the blind Go default."""
    fuel = bw.Fuel(
        opencode_free=100,
        opencode_go=50,
        opencode_models={},
        opencode_free_model_ids=("opencode/beam-free",),
    )
    assert bw.opencode_default_model(fuel) == "opencode/beam-free"


def test_opencode_default_model_per_model_exhausted_falls_back_to_free():
    """When per-model readings exist but every Go model is exhausted, pick free."""
    fuel = bw.Fuel(
        opencode_free=100,
        opencode_go=50,
        opencode_models={"glm-5.3": 0, "kimi-k3": 0},
        opencode_free_model_ids=("opencode/beam-free",),
    )
    assert bw.opencode_default_model(fuel) == "opencode/beam-free"


def test_opencode_default_model_per_model_exhausted_no_free_returns_none():
    """When per-model readings exist but every Go model is exhausted and free is unavailable, return None."""
    fuel = bw.Fuel(
        opencode_free=0,
        opencode_go=50,
        opencode_models={"glm-5.3": 0, "kimi-k3": 0},
    )
    assert bw.opencode_default_model(fuel) is None


def test_opencode_default_model_skips_paused_models(tmp_path):
    """Paused models must be skipped in favour of the next usable model."""
    state_dir = tmp_path / "state"
    now = 1_000_000.0
    bw.opencode_fuel.record_opencode_pause(
        state_dir, "opencode-go/glm-5.3", "Retry-After: 3600", now=now
    )
    fuel = bw.Fuel(
        opencode_go=50,
        opencode_models={"glm-5.3": 50, "kimi-k3": 50},
    )
    selected = bw.opencode_default_model(fuel, state_dir=state_dir, now=now)
    assert selected != "opencode-go/glm-5.3"
    assert selected == "opencode-go/kimi-k3"


def test_opencode_default_model_falls_back_to_free_when_go_paused(tmp_path):
    state_dir = tmp_path / "state"
    now = 1_000_000.0
    bw.opencode_fuel.record_opencode_pause(
        state_dir, "opencode-go/glm-5.3", "rate limit", now=now
    )
    fuel = bw.Fuel(
        opencode_free=100,
        opencode_go=50,
        opencode_models={"glm-5.3": 50},
        opencode_free_model_ids=("opencode/beam-free",),
    )
    selected = bw.opencode_default_model(fuel, state_dir=state_dir, now=now)
    assert selected == "opencode/beam-free"


def test_build_launch_opencode_creates_wrapper(tmp_path: Path):
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "Do work.", OP, tmp_path)
    assert spec.argv[0] == "powershell.exe"
    assert "launch-opencode.ps1" in spec.argv[-1]
    prompt_key = next(k for k in spec.files if k.endswith("prompt.txt"))
    script_key = next(k for k in spec.files if k.endswith("launch-opencode.ps1"))
    script = spec.files[script_key]
    assert "opencode.exe" in script or OP in script
    assert "'run', '-m', $model" in script
    assert "--continue" not in script
    assert "Write-Output $outStr" in script
    assert "$proc.WaitForExit($watchdogMs)" in script
    assert "taskkill /T /F /PID $proc.Id" in script
    assert "opencode-out-of-fuel.log" in script
    assert "record-pause" in script
    assert "--dir $pauseStateDir" in script
    assert "--model $model" in script
    # The full OpenCode output must be piped to the helper's stdin, never argv.
    assert "$outStr | & $py $pyHelper record-pause --dir $pauseStateDir --model $model | Out-Null" in script
    assert "Do work." in spec.files[prompt_key]
    # Every OpenCode launch must pass the fresh-session guard (no --continue/--session).
    ps1_files = {k: v for k, v in spec.files.items() if k.endswith(".ps1")}
    bw.assert_fresh(spec.argv, ps1_files)


def test_build_launch_opencode_wrapper_parses_as_powershell(tmp_path: Path):
    """Generated wrapper must be valid PowerShell with whitespace/quote-heavy prompts."""
    if shutil.which("powershell.exe") is None:
        pytest.skip("powershell.exe not available")
    prompt = 'Say "hello" and \'world\' with spaces'
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", prompt, OP, tmp_path)
    script_key = next(k for k in spec.files if k.endswith("launch-opencode.ps1"))
    script_path = tmp_path / "launch-opencode.ps1"
    script_path.write_text(spec.files[script_key], encoding="utf-8")

    parse_cmd = (
        "[scriptblock]::Create((Get-Content -Raw -Path "
        f"'{script_path}'" ")) | Out-Null; 'PARSED_OK'"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", parse_cmd],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "PARSED_OK" in result.stdout


def test_opencode_watchdog_kills_hanging_process_without_blocking(tmp_path: Path):
    """A timed-out opencode run must not block the seat on pipe reads."""
    if shutil.which("powershell.exe") is None:
        pytest.skip("powershell.exe not available")

    # Fake opencode.exe: ignores args and sleeps long enough to be killed.
    fake_opencode = tmp_path / "fake-opencode.ps1"
    fake_opencode.write_text(
        "Start-Sleep -Seconds 60; exit 0",
        encoding="utf-8",
    )

    # A batch wrapper lets the PowerShell wrapper invoke it like an .exe.
    fake_exe = tmp_path / "opencode.cmd"
    fake_exe.write_text(
        f"@powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"{fake_opencode}\" %*",
        encoding="utf-8",
    )

    spec = bw.build_launch(
        "opencode", "agent", r"C:\ai\bob\worker", "short watchdog please", str(fake_exe), tmp_path
    )
    script_key = next(k for k in spec.files if k.endswith("launch-opencode.ps1"))
    script_path = Path(script_key)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    for path, text in spec.files.items():
        Path(path).write_text(text, encoding="utf-8")

    env = os.environ.copy()
    env["BOB_OPENCODE_WATCHDOG_MS"] = "500"
    env["LOCALAPPDATA"] = str(tmp_path)

    start = time.time()
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
        input="exit\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    elapsed = time.time() - start

    # Must finish quickly: the 500ms watchdog plus bounded drain should dominate.
    assert elapsed < 8, f"watchdog blocked for {elapsed:.1f}s"
    # Wrapper should exit cleanly after stdin sends 'exit'.
    assert result.returncode == 0
    # The watchdog must record its timeout. A failed start or early exit writes no record.
    fuel_log = tmp_path / "Bobiverse" / "worker" / "logs" / "opencode-out-of-fuel.log"
    assert fuel_log.is_file(), "watchdog did not write a fuel log"
    assert "watchdog timeout" in fuel_log.read_text(encoding="utf-8")


def test_should_start_fuel_watcher_includes_opencode():
    assert bw.should_start_fuel_watcher("opencode") is True
    assert bw.should_start_fuel_watcher("plan") is False


def test_read_fuel_parses_opencode_section(tmp_path: Path):
    (tmp_path / "tools").mkdir()
    payload = (
        '{"ok":true,"cursor":{"high":5,"low":0},'
        '"grok":{"remaining_pct":null,"state":"unknown"},'
        '"opencode":{"free":100,"go":50,"models":{"glm-5.3":50},'
        '"free_model_ids":["opencode/beam-free"]}}'
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
    assert f.opencode_free_model_ids == ("opencode/beam-free",)


def test_agent_fuel_ps1_forwards_free_model_ids_from_opencode_fuel(tmp_path: Path):
    """Get-BobAgentFuel.ps1 must pass free_model_ids from Get-BobOpencodeFuel.ps1 into the payload."""
    if shutil.which("powershell.exe") is None:
        pytest.skip("powershell.exe not available")

    tools = tmp_path / "tools"
    src = tmp_path / "src"
    tools.mkdir()
    src.mkdir()

    agent_ps1 = Path(bw.__file__).resolve().parent.parent / "tray" / "tools" / "Get-BobAgentFuel.ps1"
    shutil.copy(agent_ps1, tools / "Get-BobAgentFuel.ps1")

    # Fake Get-BobOpencodeFuel.ps1 emits the free_model_ids the real helper would discover.
    (tools / "Get-BobOpencodeFuel.ps1").write_text(
        (
            "[Console]::Out.WriteLine("
            "'{\"free\":100,\"go\":null,\"models\":{},"
            "\"free_model_ids\":[\"opencode/beam-free\",\"opencode/iceman-contributor-free\"]}')\n"
            "exit 0"
        ),
        encoding="utf-8",
    )

    # Minimal BobBridge module so Import-Module succeeds and the Cursor/Grok readers no-op.
    (src / "BobBridge.psm1").write_text(
        "function Get-BobCursorAgentWeeklyRemaining { }\n"
        "function Get-BobCursorGroupRemainFromLocalDoc { }\n"
        "function Get-BobWeeklyRemaining { }\n"
        "function Get-BobGrokAuthSnapshot { }\n"
        "function Get-BobGrokAvailability { }\n",
        encoding="utf-8",
    )
    (src / "BobBridge.psd1").write_text(
        "@{ RootModule = 'BobBridge.psm1'; ModuleVersion = '1.0.0'; FunctionsToExport = '*' }",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tools / "Get-BobAgentFuel.ps1"),
            "-InstallRoot",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    doc = json.loads(result.stdout.strip().splitlines()[-1])
    assert doc["opencode"]["free_model_ids"] == [
        "opencode/beam-free",
        "opencode/iceman-contributor-free",
    ]


OPENCODE_FUEL_PS1 = Path(bw.__file__).resolve().parent.parent / "tray" / "tools" / "Get-BobOpencodeFuel.ps1"


def test_opencode_fuel_ps1_uses_models_plain_text_stats_for_each_window():
    text = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert text.count("stats --models --days") == 2
    assert "stats --json" not in text
    assert "--output json" not in text
    assert "Invoke-OpencodeTimed 'models'" in text
    assert "5 / 24" not in text
    assert "0.208333" not in text


def test_opencode_fuel_ps1_pipes_windowed_payload_via_stdin():
    text = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "ConvertTo-Json -Compress" in text
    assert "$payload | & $py -c $script" in text
    assert "sys.stdin.read()" in text
    assert "sys.argv[1]" not in text


def test_opencode_fuel_ps1_pythonpath_resolves_common_scripts_in_work_tree():
    text = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "common\\scripts" in text
    assert "Test-Path -LiteralPath $common -PathType Container" in text
    assert "$env:PYTHONPATH = \"$common;$env:PYTHONPATH\"" in text


def test_opencode_fuel_ps1_uses_windowed_fuel_translation():
    text = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "opencode_fuel" in text
    assert "parse_opencode_stats_text_or_json" in text
    assert "fuel_from_windowed_stats" in text


def test_opencode_fuel_ps1_resolves_installed_layout(tmp_path: Path):
    r"""The helper must find common\scripts when run from <ai root>\bob\tools."""
    if shutil.which("powershell.exe") is None:
        pytest.skip("powershell.exe not available")
    installed = tmp_path / "bob"
    tools = installed / "tools"
    common_scripts = installed / "common" / "scripts"
    tools.mkdir(parents=True)
    common_scripts.mkdir(parents=True)

    script_dst = tools / "Get-BobOpencodeFuel.ps1"
    script_dst.write_text(OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")

    fuel_py_src = Path(bw.__file__).resolve().parent.parent.parent / "common" / "scripts" / "opencode_fuel.py"
    shutil.copy(fuel_py_src, common_scripts / "opencode_fuel.py")

    fixture = '{"costs": {"glm-5.3": 7.5}, "free_models": ["beam-free"]}'
    env = os.environ.copy()
    env["BOB_OPENCODE_FUEL_FIXTURE"] = fixture
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_dst)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout.strip().splitlines()[-1])
    assert parsed["go"] == 50
    assert parsed["free"] == 100
