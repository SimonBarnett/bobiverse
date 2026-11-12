"""Tests for OpenCode worker seat wiring (issue #6120)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import bob.scripts.bob_worker as bw
from test_fr6159_oc_pack_layout import _opencode_fuel_fixture_env, _run_opencode_fuel_ps


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
    # FR #6156: idle/output heartbeat, not absolute WaitForExit($watchdogMs).
    assert "$proc.WaitForExit($watchdogMs)" not in script
    assert "RedirectStandardOutput" in script
    assert "$lastBeat" in script
    assert "$lastLen" in script
    assert "taskkill /T /F /PID $proc.Id" in script
    assert "opencode-out-of-fuel.log" in script
    assert "record-pause" in script
    assert "--dir $pauseStateDir" in script
    assert "--model $model" in script
    # The full OpenCode output must be piped to the helper's stdin, never argv.
    assert "$scan | & $py $pyHelper record-pause --dir $pauseStateDir --model $model 2>&1 | Out-String" in script
    assert "Replace([string]$line, ' ')" in script
    assert "[regex]::Replace($scan, '`[^`]*`', ' ')" in script
    assert "$ErrorActionPreference = 'Continue'" in script
    assert "$recordExit = $LASTEXITCODE" in script
    assert "record-pause helper failed" in script
    assert "BOB_OPENCODE_MODEL is required" in script
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
    assert result.returncode == 0, (result.stderr or result.stdout or "<no output>")[:800]
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
    env["BOB_OPENCODE_MODEL"] = "opencode/beam-free"

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
    assert elapsed < 12, f"watchdog blocked for {elapsed:.1f}s"
    # Wrapper should exit cleanly after stdin sends 'exit'.
    assert result.returncode == 0
    # The watchdog must record its timeout. A failed start or early exit writes no record.
    fuel_log = tmp_path / "Bobiverse" / "worker" / "logs" / "opencode-out-of-fuel.log"
    assert fuel_log.is_file(), "watchdog did not write a fuel log"
    assert "watchdog timeout" in fuel_log.read_text(encoding="utf-8")



def test_fr6156_opencode_wrapper_uses_idle_watchdog_not_wall_clock(tmp_path: Path):
    """Generated wrapper must poll idle/no-output, not absolute WaitForExit(watchdogMs)."""
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "idle watchdog", OP, tmp_path)
    script_key = next(k for k in spec.files if k.endswith("launch-opencode.ps1"))
    script = spec.files[script_key]
    assert "RedirectStandardOutput" in script
    assert "$lastBeat" in script
    assert "idleMs" in script
    assert "$proc.WaitForExit($watchdogMs)" not in script
    worker_src = Path(__file__).resolve().parents[1] / "scripts" / "bob_worker.py"
    assert "FR #6156" in worker_src.read_text(encoding="utf-8")


def test_mrb6163_opencode_start_process_uses_argstr(tmp_path: Path):
    """MRB #6163: Start-Process must take quoted $argStr (array ArgumentList splits prompts)."""
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", 'Say "hi" please', OP, tmp_path)
    script = next(v for k, v in spec.files.items() if k.endswith("launch-opencode.ps1"))
    assert "Start-Process -FilePath $exe -ArgumentList $argStr" in script
    assert "Start-Process -FilePath $exe -ArgumentList $argList" not in script
    assert "$argStr =" in script


def test_mrb6163_opencode_prompt_with_spaces_reaches_child(tmp_path: Path):
    """Behavioral: prompt with spaces/quotes must arrive as one argv token to the child."""
    if shutil.which("powershell.exe") is None:
        pytest.skip("powershell.exe not available")

    argv_log = tmp_path / "argv-log.txt"
    fake_opencode = tmp_path / "fake-opencode-argv.ps1"
    log_path = str(argv_log).replace("'", "''")
    ps1_body = (
        "$log = '" + log_path + "'\n"
        + "$args | ForEach-Object { Add-Content -LiteralPath $log -Value $_ }\n"
        + "Write-Output 'ok'\n"
        + "exit 0\n"
    )
    fake_opencode.write_text(ps1_body, encoding="utf-8")
    fake_exe = tmp_path / "opencode.cmd"
    fake_exe.write_text(
        '@powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{ps1}" %*\n'.format(
            ps1=str(fake_opencode)
        ),
        encoding="utf-8",
    )

    prompt = 'Say "hello world" and keep going'
    spec = bw.build_launch(
        "opencode", "agent", r"C:\ai\bob\worker", prompt, str(fake_exe), tmp_path
    )
    script_key = next(k for k in spec.files if k.endswith("launch-opencode.ps1"))
    for path, body in spec.files.items():
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    env = os.environ.copy()
    env["BOB_OPENCODE_WATCHDOG_MS"] = "5000"
    env["LOCALAPPDATA"] = str(tmp_path)
    env["BOB_OPENCODE_MODEL"] = "opencode/beam-free"

    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_key)],
        input="exit\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (result.stderr or result.stdout or "<no output>")[:800]
    assert argv_log.is_file(), "child never logged argv"
    lines = [ln.rstrip("\r") for ln in argv_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert "run" in lines
    assert "-m" in lines
    assert "opencode/beam-free" in lines
    assert prompt in lines, f"prompt split or stripped; argv={lines!r}"



def test_fr6156_opencode_watchdog_allows_long_run_with_output(tmp_path: Path):
    """Flushed ticks inside the idle cap must finish a run longer than that cap (FR #6156).

    The production loop is unchanged: a child whose redirected stdout and stderr
    stay the same length for ``BOB_OPENCODE_WATCHDOG_MS`` is still killed. A
    silent live child is not treated as progress.

    The old fixture used buffered ``Write-Output`` every 150ms against a 2s cap.
    Nested powershell cold start can leave that redirect file unchanged for
    longer than 2s, so the idle kill fired before any tick was visible (runs
    of about 7s that logged ``watchdog timeout (no output)``). This child
    flushes a line as soon as the script is executing. The cap is above that
    cold start. Later gaps stay far under the cap, and the series lasts longer
    than the cap, so a wall-clock kill would have stopped it.
    """
    if shutil.which("powershell.exe") is None:
        pytest.skip("powershell.exe not available")

    watchdog_ms = 8000
    tick_ms = 250
    tick_count = 40  # 10s of gaps after the first flushed line
    assert tick_ms * tick_count > watchdog_ms
    assert tick_ms * 4 < watchdog_ms

    fake_opencode = tmp_path / "fake-opencode-ticks.ps1"
    fake_opencode.write_text(
        "\n".join([
            "[Console]::Out.WriteLine('tick-start')",
            "[Console]::Out.Flush()",
            f"1..{tick_count} | ForEach-Object {{",
            "    [Console]::Out.WriteLine('tick ' + $_)",
            "    [Console]::Out.Flush()",
            f"    Start-Sleep -Milliseconds {tick_ms}",
            "}",
            "exit 0",
            "",
        ]),
        encoding="utf-8",
    )
    fake_exe = tmp_path / "opencode.cmd"
    fake_exe.write_text(
        f'@powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{fake_opencode}" %*\n',
        encoding="utf-8",
    )

    spec = bw.build_launch(
        "opencode", "agent", r"C:\ai\bob\worker", "keep ticking", str(fake_exe), tmp_path
    )
    script_key = next(k for k in spec.files if k.endswith("launch-opencode.ps1"))
    for path, body in spec.files.items():
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    # Production idle compare stays a length gap, not a wall-clock WaitForExit.
    wrapper = Path(script_key).read_text(encoding="utf-8")
    assert "if ($idleMs -ge $watchdogMs)" in wrapper
    assert "$proc.WaitForExit($watchdogMs)" not in wrapper

    env = os.environ.copy()
    env["BOB_OPENCODE_WATCHDOG_MS"] = str(watchdog_ms)
    env["LOCALAPPDATA"] = str(tmp_path)
    env["BOB_OPENCODE_MODEL"] = "opencode/beam-free"

    start = time.time()
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_key)],
        input="exit\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    elapsed = time.time() - start
    assert result.returncode == 0, (result.stderr or result.stdout or "<no output>")[:800]
    assert elapsed > (watchdog_ms / 1000.0), f"run ended before the idle cap ({elapsed:.1f}s)"
    fuel_log = tmp_path / "Bobiverse" / "worker" / "logs" / "opencode-out-of-fuel.log"
    if fuel_log.is_file():
        blob = fuel_log.read_text(encoding="utf-8")
        assert "watchdog timeout" not in blob, blob
    combined = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
    assert "tick-start" in combined
    assert f"tick {tick_count}" in combined


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
    assert "StandardInput" in text
    assert "utf-8-sig" in text
    assert "UTF8Encoding $false" in text
    assert "BaseStream.Write" in text
    assert "sys.stdin.read()" not in text
    assert "sys.argv[1]" not in text
    # FR #6717 / #6727: PATHEXT .EXE ensure + ProcessStartInfo stats child (no & $py).
    assert "python_exit" in text
    assert "stats_error" in text
    assert "PATHEXT" in text
    assert ".EXE" in text
    assert "BOBIVERSE_PYTHON" in text
    assert "ProcessStartInfo" in text
    assert "bob-oc-stats-" in text
    assert "$payload | & $py -c $script" not in text


def test_opencode_fuel_ps1_pythonpath_resolves_common_scripts_in_work_tree():
    """FR #6159: resolve opencode_fuel.py as a file (scripts\\ then common\\scripts\\)."""
    text = OPENCODE_FUEL_PS1.read_text(encoding="utf-8-sig")
    assert "scripts\\opencode_fuel.py" in text
    assert "common\\scripts\\opencode_fuel.py" in text
    assert "PathType Leaf" in text
    assert "$env:PYTHONPATH = \"$pyDir;$env:PYTHONPATH\"" in text


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

    # FR #6670 / #6677 / FR #6701: same scrub + explicit interpreter as FR #6159.
    env = _opencode_fuel_fixture_env()
    parsed = _run_opencode_fuel_ps(script_dst, env=env, cwd=tmp_path)
    assert parsed.get("read_state") == "ok"
    assert parsed["go"] == 50
    assert parsed["free"] == 100


def test_resolve_opencode_fuel_helper_path_repo_layout(tmp_path: Path):
    """In a repo/worktree layout the helper lives at repo-root/common/scripts."""
    repo = tmp_path / "repo"
    source = repo / "bob" / "scripts" / "bob_worker.py"
    source.parent.mkdir(parents=True)
    source.write_text("# worker", encoding="utf-8")
    helper = repo / "common" / "scripts" / "opencode_fuel.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("# helper", encoding="utf-8")

    resolved = bw._resolve_opencode_fuel_helper_path(source_file=str(source))
    assert resolved == helper.resolve()
    assert resolved.is_absolute()


def test_resolve_opencode_fuel_helper_path_installed_layout(tmp_path: Path):
    r"""In the installed Bob layout the helper is under <ai root>\bob\common\scripts."""
    install = tmp_path / "bob"
    source = install / "bob" / "scripts" / "bob_worker.py"
    source.parent.mkdir(parents=True)
    source.write_text("# worker", encoding="utf-8")
    helper = install / "common" / "scripts" / "opencode_fuel.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("# helper", encoding="utf-8")

    resolved = bw._resolve_opencode_fuel_helper_path(source_file=str(source))
    assert resolved == helper.resolve()


def test_resolve_opencode_fuel_helper_path_fallback_to_cwd(tmp_path: Path):
    """If the source-based candidates are missing, fall back to cwd.parent/common/scripts."""
    source = tmp_path / "bob" / "scripts" / "bob_worker.py"
    source.parent.mkdir(parents=True)
    source.write_text("# worker", encoding="utf-8")
    cwd = tmp_path / "jeeves"
    cwd.mkdir()
    helper = tmp_path / "common" / "scripts" / "opencode_fuel.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("# helper", encoding="utf-8")

    resolved = bw._resolve_opencode_fuel_helper_path(cwd=str(cwd), source_file=str(source))
    assert resolved == helper.resolve()


def test_build_launch_opencode_wrapper_embeds_absolute_helper_path(tmp_path: Path):
    """The wrapper must embed an absolute helper path resolved at generation time."""
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "Do work.", OP, tmp_path)
    script = next(v for k, v in spec.files.items() if k.endswith("launch-opencode.ps1"))
    helper_path = bw._resolve_opencode_fuel_helper_path(cwd=r"C:\ai\bob\worker")
    assert f"$pyHelper = '{str(helper_path).replace(chr(39), chr(39)*2)}'" in script
    assert helper_path.is_absolute()
    assert helper_path.name == "opencode_fuel.py"


def test_build_launch_opencode_wrapper_checks_record_pause_exit_code(tmp_path: Path):
    """A failing record-pause helper must be logged so the pause is not silently dropped."""
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "Do work.", OP, tmp_path)
    script = next(v for k, v in spec.files.items() if k.endswith("launch-opencode.ps1"))
    assert "$recordExit = $LASTEXITCODE" in script
    assert "if ($recordExit -ne 0)" in script
    assert "record-pause helper failed" in script
    assert "Add-Content -Path $fuelLog" in script


def test_opencode_has_tokens_ignores_aggregate_when_per_model_exhausted():
    """Aggregate go>0 must not keep OpenCode selectable when every Go model is 0 and free is 0."""
    fuel = bw.Fuel(
        opencode_free=0,
        opencode_go=50,
        opencode_models={"glm-5.3": 0, "kimi-k3": 0},
    )
    assert bw.opencode_has_tokens(fuel) is False
    assert bw.opencode_default_model(fuel) is None
    assert bw.select_agent(fuel, None, None, OP).kind == "none"


def test_build_launch_opencode_wrapper_requires_model_env(tmp_path: Path):
    """Wrapper must require BOB_OPENCODE_MODEL; never hard-code exhausted glm-5.3."""
    spec = bw.build_launch("opencode", "agent", r"C:\ai\bob\worker", "Do work.", OP, tmp_path)
    script = next(v for k, v in spec.files.items() if k.endswith("launch-opencode.ps1"))
    assert "BOB_OPENCODE_MODEL is required" in script
    assert "else { 'opencode-go/glm-5.3' }" not in script

