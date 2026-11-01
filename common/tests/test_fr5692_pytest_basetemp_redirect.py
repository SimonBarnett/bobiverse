"""FR #5692: locked pytest-of-* must not break tmp_path; redirect basetemp."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import crash_report


def test_fr5692_usable_root_returns_true():
    # Do not use tmp_path here: that fixture is what hangs on a locked pytest-of-*.
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="fr5692-ok-"))
    try:
        assert crash_report.pytest_temp_root_is_usable(root, timeout_s=2.0) is True
    finally:
        try:
            root.rmdir()
        except OSError:
            pass


def test_fr5692_access_denied_returns_false():
    def boom(_path: Path) -> None:
        err = PermissionError("[WinError 5] Access is denied")
        err.winerror = 5
        raise err

    assert (
        crash_report.pytest_temp_root_is_usable(
            Path("D:/Temp/pytest-of-locked"),
            timeout_s=1.0,
            probe_fn=boom,
        )
        is False
    )


def test_fr5692_probe_timeout_returns_false():
    import time

    def hang(_path: Path) -> None:
        time.sleep(5.0)

    assert (
        crash_report.pytest_temp_root_is_usable(
            Path("D:/Temp/pytest-of-hang"),
            timeout_s=0.2,
            probe_fn=hang,
        )
        is False
    )


def test_fr5692_ensure_sets_basetemp_when_default_unusable(monkeypatch):
    import tempfile

    lad = Path(tempfile.mkdtemp(prefix="fr5692-lad-"))
    monkeypatch.setenv("LOCALAPPDATA", str(lad))
    monkeypatch.setattr(
        crash_report,
        "default_pytest_of_root",
        lambda: Path("D:/Temp/pytest-of-locked"),
    )
    monkeypatch.setattr(
        crash_report,
        "pytest_temp_root_is_usable",
        lambda *_a, **_k: False,
    )
    cfg = SimpleNamespace(option=SimpleNamespace(basetemp=None))
    got = crash_report.ensure_writable_pytest_basetemp(cfg, timeout_s=0.5)
    assert got
    assert cfg.option.basetemp == got
    assert Path(got).is_dir()
    assert "pytest-basetemp-" in got.replace("\\", "/")


def test_fr5692_ensure_noop_when_basetemp_already_set(monkeypatch):
    monkeypatch.setattr(
        crash_report,
        "pytest_temp_root_is_usable",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not probe")),
    )
    cfg = SimpleNamespace(option=SimpleNamespace(basetemp=r"D:\Temp\already"))
    assert crash_report.ensure_writable_pytest_basetemp(cfg) is None
    assert cfg.option.basetemp == r"D:\Temp\already"


def test_fr5692_ensure_noop_when_default_ok(monkeypatch):
    monkeypatch.setattr(
        crash_report,
        "default_pytest_of_root",
        lambda: Path("D:/Temp/pytest-of-ok-fake"),
    )
    monkeypatch.setattr(
        crash_report,
        "pytest_temp_root_is_usable",
        lambda *_a, **_k: True,
    )
    cfg = SimpleNamespace(option=SimpleNamespace(basetemp=None))
    assert crash_report.ensure_writable_pytest_basetemp(cfg) is None
    assert cfg.option.basetemp is None


def test_mrb5693_root_conftest_wires_ensure():
    """Hostile MRB #5693: root conftest must call ensure_writable_pytest_basetemp."""
    root = Path(__file__).resolve().parents[2] / "conftest.py"
    src = root.read_text(encoding="utf-8")
    assert "ensure_writable_pytest_basetemp" in src
    assert "FR #5692" in src
    assert src.endswith("\n")
