"""FR #8202: frozen worker prefers hash-checked shipped scripts over flat install copies."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import worker_shipped_scripts as ship


def test_fr8202_flat_override_env_defaults_off(monkeypatch):
    monkeypatch.delenv(ship.FLAT_OVERRIDE_ENV, raising=False)
    assert ship.use_flat_scripts_override({}) is False
    assert ship.use_flat_scripts_override({ship.FLAT_OVERRIDE_ENV: "1"}) is True
    assert ship.use_flat_scripts_override({ship.FLAT_OVERRIDE_ENV: "true"}) is True
    assert ship.use_flat_scripts_override({ship.FLAT_OVERRIDE_ENV: "0"}) is False


def test_fr8202_frozen_prefers_exe_scripts_over_flat_install(tmp_path, monkeypatch):
    """Older flat C:\\ai\\bob\\scripts copy must lose to <exe>\\scripts when frozen."""
    install = tmp_path / "ai" / "bob"
    flat = install / "scripts"
    flat.mkdir(parents=True)
    (flat / "opencode_turn_guard.py").write_text("# STALE FLAT\n", encoding="utf-8")

    exe_dir = tmp_path / "Bobiverse" / "worker" / "bin"
    shipped = exe_dir / "scripts"
    shipped.mkdir(parents=True)
    (shipped / "opencode_turn_guard.py").write_text("# SHIPPED\n", encoding="utf-8")
    exe = exe_dir / "bob-worker.exe"
    exe.write_bytes(b"MZ")

    monkeypatch.setattr(bw.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bw.sys, "executable", str(exe))
    monkeypatch.delenv(ship.FLAT_OVERRIDE_ENV, raising=False)
    monkeypatch.setattr(
        bw,
        "_path_is_mei_extract",
        lambda p: "_MEI" in str(p),
    )
    # extract is no-op without MEIPASS bundle
    monkeypatch.setattr(ship, "extract_bundled_scripts", lambda: [])

    got = bw._resolve_installed_worker_script(
        "opencode_turn_guard.py",
        cwd=str(tmp_path / "run"),
        install_root=str(install),
        source_file=str(tmp_path / "_MEI999" / "bob_worker.py"),
    )
    assert got == (shipped / "opencode_turn_guard.py").resolve()
    assert got.read_text(encoding="utf-8") == "# SHIPPED\n"


def test_fr8202_flat_override_lets_install_win(tmp_path, monkeypatch):
    install = tmp_path / "ai" / "bob"
    flat = install / "scripts"
    flat.mkdir(parents=True)
    (flat / "opencode_turn_guard.py").write_text("# FLAT DEV\n", encoding="utf-8")

    exe_dir = tmp_path / "bin"
    shipped = exe_dir / "scripts"
    shipped.mkdir(parents=True)
    (shipped / "opencode_turn_guard.py").write_text("# SHIPPED\n", encoding="utf-8")
    exe = exe_dir / "bob-worker.exe"
    exe.write_bytes(b"MZ")

    monkeypatch.setattr(bw.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bw.sys, "executable", str(exe))
    monkeypatch.setenv(ship.FLAT_OVERRIDE_ENV, "1")
    monkeypatch.setattr(ship, "extract_bundled_scripts", lambda: [])

    got = bw._resolve_installed_worker_script(
        "opencode_turn_guard.py",
        install_root=str(install),
        source_file=str(exe_dir / "bob_worker.py"),
    )
    assert got == (flat / "opencode_turn_guard.py").resolve()


def test_fr8202_extract_overwrites_stale_bin_scripts(tmp_path, monkeypatch):
    bundle = tmp_path / "mei" / ship.BUNDLE_DIR_NAME
    bundle.mkdir(parents=True)
    (bundle / "crash_report.py").write_text("# BUNDLE v2\n", encoding="utf-8")

    exe_dir = tmp_path / "bin"
    dest = exe_dir / "scripts"
    dest.mkdir(parents=True)
    (dest / "crash_report.py").write_text("# STALE v1\n", encoding="utf-8")
    exe = exe_dir / "bob-worker.exe"
    exe.write_bytes(b"MZ")

    monkeypatch.setattr(ship.sys, "frozen", True, raising=False)
    monkeypatch.setattr(ship.sys, "_MEIPASS", str(tmp_path / "mei"), raising=False)
    monkeypatch.setattr(ship.sys, "executable", str(exe))

    result = ship.extract_bundled_scripts_result()
    assert "crash_report.py" in result.overwritten
    assert result.failed == []
    assert (dest / "crash_report.py").read_text(encoding="utf-8") == "# BUNDLE v2\n"
    assert result.hashes["crash_report.py"]


def test_fr8202_extract_reports_when_overwrite_blocked(tmp_path, monkeypatch):
    bundle = tmp_path / "mei" / ship.BUNDLE_DIR_NAME
    bundle.mkdir(parents=True)
    (bundle / "runtime_failure.py").write_text("# BUNDLE\n", encoding="utf-8")

    exe_dir = tmp_path / "bin"
    dest = exe_dir / "scripts"
    dest.mkdir(parents=True)
    stale = dest / "runtime_failure.py"
    stale.write_text("# STALE\n", encoding="utf-8")
    exe = exe_dir / "bob-worker.exe"
    exe.write_bytes(b"MZ")

    monkeypatch.setattr(ship.sys, "frozen", True, raising=False)
    monkeypatch.setattr(ship.sys, "_MEIPASS", str(tmp_path / "mei"), raising=False)
    monkeypatch.setattr(ship.sys, "executable", str(exe))

    real_write = Path.write_bytes

    def blocked(self, data):
        if self.name == "runtime_failure.py":
            raise OSError("Access is denied")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", blocked)
    result = ship.extract_bundled_scripts_result()
    assert any(n == "runtime_failure.py" for n, _ in result.failed)
    assert stale.read_text(encoding="utf-8") == "# STALE\n"


def test_fr8202_short_hash_stable():
    h = ship.short_content_hash(b"hello")
    assert len(h) == 12
    assert h == ship.short_content_hash(b"hello")
    assert h != ship.short_content_hash(b"world")
