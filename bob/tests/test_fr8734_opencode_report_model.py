"""FR #8734 / BOB-29: session and tray logs name the launched OpenCode model."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = "opencode/deepseek-v4.1-flash-free"


def _worker() -> str:
    return (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")


def test_fr8734_start_agent_writes_seat_model_line():
    src = _worker()
    start = src.index('self.session_log.write("start"')
    window = src[start:start + 700]
    assert 'f"opencode model={oc_id}"' in window
    assert 'child.get("env")' in window


def test_fr8734_wrapper_prints_model_and_builds_arglist_after_pause():
    src = _worker()
    fn = src.index("function Invoke-OpencodeRun")
    body = src[fn:src.index("function ", fn + 10)]
    pause = body.index("BOB_OPENCODE_PAUSE_FALLBACK")
    arg = body.index("$argList = @('run', '--dir', $ocDir, '-m', $model, $line)", pause)
    line = body.index("opencode-run model=", arg)
    launch = body.index("Start-Process -FilePath $exe", line)
    assert pause < arg < line < launch


def test_fr8734_tray_log_names_model_before_start():
    cs = (ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs").read_text(encoding="utf-8")
    ps1 = (ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    assert '"action", "model"' in cs
    assert '"model", model' in cs
    assert "workers-opencode model=" in ps1
    assert MODEL in ps1
    start = ps1.index("workers-opencode model=")
    launch = ps1.index("Start-BobTrayWorkerExe -Mode 'agent' -Agent 'opencode'", start)
    assert start < launch


def test_fr8734_docs_name_the_seat_log_route():
    doc = (ROOT / "bob" / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "opencode model=" in doc
    assert "opencode-run model=" in doc
    assert "watch_bob_tray.log" in doc
