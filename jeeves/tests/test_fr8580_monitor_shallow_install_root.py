"""FR #8580: monitor path helpers tolerate shallow install roots (J:\\tools\\monitor)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MON))

import _common as common  # noqa: E402
import github_resync_focus as grf  # noqa: E402
import intake_allowlist as ial  # noqa: E402


def test_find_upward_file_stops_at_root_without_indexerror(tmp_path: Path):
    shallow = tmp_path / "tools" / "monitor"
    shallow.mkdir(parents=True)
    # No intake.py anywhere above — must return None, never IndexError
    assert common.find_upward_file(shallow, "common", "scripts", "intake.py") is None
    assert common.find_upward_file(shallow, "scripts", "intake.py") is None


def test_find_upward_file_finds_flat_install_layout(tmp_path: Path):
    root = tmp_path / "install"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    marker = scripts / "intake.py"
    marker.write_text("# probe\n", encoding="utf-8")
    monitor = root / "tools" / "monitor"
    monitor.mkdir(parents=True)
    found = common.find_upward_file(monitor, "scripts", "intake.py")
    assert found == marker.resolve()


def test_find_intake_py_shallow_tree_no_indexerror(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOB_INTAKE_PY", raising=False)
    shallow = tmp_path / "tools" / "monitor"
    shallow.mkdir(parents=True)
    # Empty shallow walk must not IndexError (find_intake_py may still fall back to repo __file__)
    assert common.find_upward_file(shallow, "scripts", "intake.py") is None
    assert common.find_upward_file(shallow, "common", "scripts", "intake.py") is None
    # Prefer start= flat scripts/ over the repo copy next to the package
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    target = scripts / "intake.py"
    target.write_text(
        'DEFAULT_ALLOW_REPOS = frozenset({"SimonBarnett/bobiverse"})\n',
        encoding="utf-8",
    )
    got = ial.find_intake_py(start=shallow)
    assert got == target.resolve()


def test_ensure_common_shallow_tree_no_indexerror(tmp_path: Path):
    monitor = tmp_path / "tools" / "monitor"
    monitor.mkdir(parents=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "chair_health.py").write_text("x = 1\n", encoding="utf-8")
    before = list(sys.path)
    try:
        # Call with explicit start so we do not depend on package __file__ location
        found = common.ensure_script_dir_on_path("chair_health.py", start=monitor)
        assert found == scripts.resolve()
    finally:
        sys.path[:] = before
        sys.modules.pop("chair_health", None)


def test_github_resync_ensure_common_on_shallow_copy(tmp_path: Path):
    """Copy github_resync_focus into a 2-level tree and import _ensure_common."""
    monitor = tmp_path / "tools" / "monitor"
    monitor.mkdir(parents=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "chair_health.py").write_text("def discover_repos(*a, **k):\n    return []\n", encoding="utf-8")
    # Minimal stubs so import works
    shutil.copy2(MON / "_common.py", monitor / "_common.py")
    src = (MON / "github_resync_focus.py").read_text(encoding="utf-8")
    (monitor / "github_resync_focus.py").write_text(src, encoding="utf-8")
    # Run ensure via subprocess so sys.path isolation is clean
    code = (
        "import sys; from pathlib import Path; "
        f"sys.path.insert(0, r'{monitor}'); "
        "import github_resync_focus as m; m._ensure_common(); "
        "import chair_health; print('OK')"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(monitor),
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "OK" in r.stdout


def test_monitor_checks_dry_run_exit0_from_shallow_cwd(tmp_path: Path):
    """Invoke scripts with cwd under a shallow tree; --dry-run must exit 0 (no IndexError)."""
    monitor = tmp_path / "tools" / "monitor"
    monitor.mkdir(parents=True)
    for name in (
        "_common.py",
        "intake_allowlist.py",
        "github_resync_focus.py",
        "needs_human_false_positive.py",
        "open_pr_mrb_missing.py",
        "open_pr_stale_base.py",
    ):
        shutil.copy2(MON / name, monitor / name)
    for name in (
        "intake_allowlist.py",
        "github_resync_focus.py",
        "needs_human_false_positive.py",
        "open_pr_mrb_missing.py",
        "open_pr_stale_base.py",
    ):
        r = subprocess.run(
            [sys.executable, str(monitor / name), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(monitor),
        )
        assert r.returncode == 0, (name, r.stderr, r.stdout)
        payload = json.loads(r.stdout.strip().splitlines()[-1])
        assert payload["ok"] is True
        assert payload["dry_run"] is True


def test_source_no_longer_indexes_deep_parents():
    for name in (
        "intake_allowlist.py",
        "github_resync_focus.py",
        "idle_seats.py",
        "queue_flow.py",
        "wake_grok_bot_bob.py",
        # FR #8591 siblings still on parents[N] after #8580
        "needs_human_false_positive.py",
        "open_pr_mrb_missing.py",
        "open_pr_stale_base.py",
    ):
        text = (MON / name).read_text(encoding="utf-8")
        assert "parents[2]" not in text, name
        assert "parents[3]" not in text, name
        assert "parents[1]" not in text, name
