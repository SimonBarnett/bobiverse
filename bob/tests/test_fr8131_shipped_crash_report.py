"""FR #8131: installed OpenCode seats must import crash_report, or stay up without a log.

The installed worker runs opencode_stdout_log.py from bin\\scripts. That folder
has no common/scripts tree. Shipping crash_report.py beside it is the happy
path. If the redactor is still missing, the script prints one WARN and exits
0. It must not raise ModuleNotFoundError and must not write an unredacted log.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import worker_shipped_scripts as ship

from repo_layout import ROOT

BOB_SCRIPTS = ROOT / "bob" / "scripts"
WORKER = BOB_SCRIPTS / "bob_worker.py"
LOG = BOB_SCRIPTS / "opencode_stdout_log.py"


def _clean_env(extra: dict | None = None) -> dict:
    env = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "LOCALAPPDATA": os.environ.get("TEMP", ""),
    }
    if extra:
        env.update(extra)
    return env


def test_fr8131_ships_crash_report_with_stdout_log():
    names = ship.shipped_script_names(WORKER, BOB_SCRIPTS)
    assert "opencode_stdout_log.py" in names
    assert "crash_report.py" in names
    found = ship.find_module_file("crash_report.py", BOB_SCRIPTS)
    assert found is not None
    assert found.name == "crash_report.py"
    assert "common" in found.parts


def test_fr8131_import_each_shipped_script_without_repo(tmp_path: Path):
    """Build gate: a copy of dist scripts imports with no repo on sys.path."""
    dest = tmp_path / "scripts"
    names = ship.copy_by_path_scripts(WORKER, BOB_SCRIPTS, dest)
    assert (dest / "crash_report.py").is_file()
    env = _clean_env({"PYTHONPATH": str(dest)})
    failed: list[str] = []
    for name in names:
        mod = name[:-3]
        proc = subprocess.run(
            [sys.executable, "-c", "import " + mod],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            failed.append("%s\n%s" % (name, (proc.stderr or proc.stdout)[-500:]))
    assert not failed, "unshipped import:\n" + "\n".join(failed)


def test_fr8131_missing_redactor_warns_and_does_not_traceback(tmp_path: Path):
    """The redqueen traceback: ModuleNotFoundError: No module named 'crash_report'."""
    scripts = tmp_path / "worker" / "bin" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "opencode_stdout_log.py").write_bytes(LOG.read_bytes())
    log_root = tmp_path / "local"
    env = _clean_env(
        {
            "LOCALAPPDATA": str(log_root),
            "BOB_OC_LOG_JOB": "FR SimonBarnett/bobiverse#8131",
            "BOB_OC_LOG_SEAT": "seat",
            "BOB_OC_LOG_MODEL": "example",
            "PYTHONPATH": "",
        }
    )
    proc = subprocess.run(
        [sys.executable, str(scripts / "opencode_stdout_log.py"), "open"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Traceback" not in proc.stderr
    assert proc.stderr.count("WARN opencode_stdout_log:") == 1
    assert "No module named 'crash_report'" in proc.stderr
    assert proc.stdout.strip() == ""
    assert not list(log_root.rglob("*.log"))

    again = subprocess.run(
        [sys.executable, str(scripts / "opencode_stdout_log.py"), "open"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert again.returncode == 0
    assert again.stderr.count("WARN opencode_stdout_log:") == 1


def test_fr8131_shipped_copy_redacts(tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "opencode_stdout_log.py").write_bytes(LOG.read_bytes())
    crash = ship.find_module_file("crash_report.py", BOB_SCRIPTS)
    assert crash is not None
    (scripts / "crash_report.py").write_bytes(crash.read_bytes())
    log_root = tmp_path / "local"
    env = _clean_env(
        {
            "LOCALAPPDATA": str(log_root),
            "PYTHONPATH": "",
            "BOB_OC_LOG_JOB": "FR SimonBarnett/bobiverse#8131",
            "BOB_OC_LOG_SEAT": "seat",
            "BOB_OC_LOG_MODEL": "example",
        }
    )
    opened = subprocess.run(
        [sys.executable, str(scripts / "opencode_stdout_log.py"), "open"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert opened.returncode == 0, opened.stderr
    assert "WARN" not in opened.stderr
    path = opened.stdout.strip()
    assert path.endswith(".log")
    slice_file = tmp_path / "slice.txt"
    slice_file.write_text("password=EXAMPLE\n", encoding="utf-8")
    appended = subprocess.run(
        [
            sys.executable,
            str(scripts / "opencode_stdout_log.py"),
            "append",
            path,
            str(slice_file),
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert appended.returncode == 0, appended.stderr
    body = Path(path).read_text(encoding="utf-8")
    assert "EXAMPLE" not in body
    assert "redacted" in body
