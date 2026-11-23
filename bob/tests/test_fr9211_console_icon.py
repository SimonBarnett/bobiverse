"""FR #9211: Win11 bob-worker / OpenCode seat console icons (AUMID + path find + OC launch)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REPO = ROOT.parent
sys.path.insert(0, str(SCRIPTS))


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_fr9211_find_window_icon_prefers_opencode_favicon(tmp_path):
    import bob_worker as bw

    inst = tmp_path / "inst"
    (inst / "assets").mkdir(parents=True)
    (inst / "assets" / "bob-systray.ico").write_bytes(b"bob")
    (inst / "assets" / "opencode-favicon.ico").write_bytes(b"oc")
    assert bw.find_window_icon(inst, kind="opencode") == inst / "assets" / "opencode-favicon.ico"
    assert bw.find_window_icon(inst, kind="grok") == inst / "assets" / "bob-systray.ico"


def test_fr9211_find_window_icon_jeeves_assets_and_tray(tmp_path):
    import bob_worker as bw

    inst = tmp_path / "bob"
    (inst / "jeeves" / "assets").mkdir(parents=True)
    (inst / "tray" / "assets").mkdir(parents=True)
    butler = inst / "jeeves" / "assets" / "jeeves-butler.ico"
    butler.write_bytes(b"butler")
    assert bw.find_window_icon(inst, kind="monitor") == butler
    oc = inst / "tray" / "assets" / "opencode-favicon.ico"
    oc.write_bytes(b"oc")
    assert bw.find_window_icon(inst, kind="opencode") == oc


def test_fr9211_aumid_by_kind():
    import bob_worker as bw

    assert bw._window_icon_aumid("opencode") == "Bobiverse.OpenCode"
    assert bw._window_icon_aumid("monitor") == "Bobiverse.Jeeves"
    assert bw._window_icon_aumid("grok") == "Bobiverse.BobWorker"
    assert bw._window_icon_aumid(None) == "Bobiverse.BobWorker"


def test_fr9211_set_console_icon_logs_and_never_raises(tmp_path):
    import bob_worker as bw

    lines: list = []
    ok = bw.set_console_icon(tmp_path / "nowhere", kind="opencode", log=lines.append)
    assert ok in (True, False)
    assert lines, "expected a console-icon log line"
    assert any("console-icon:" in x for x in lines)


def test_fr9211_launch_opencode_embeds_console_icon_helper(tmp_path):
    import bob_worker as bw

    inst = tmp_path / "inst"
    (inst / "assets").mkdir(parents=True)
    ico = inst / "assets" / "opencode-favicon.ico"
    ico.write_bytes(b"oc")
    run = tmp_path / "run"
    run.mkdir()
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(tmp_path / "cwd"),
        "hello",
        "opencode.exe",
        run,
        install_root=str(inst),
    )
    script = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert "Set-BobConsoleIcon" in script
    assert "Bobiverse.OpenCode" in script
    assert "SetCurrentProcessExplicitAppUserModelID" in script
    assert "opencode-favicon.ico" in script
    assert "console-icon:" in script
    assert str(ico).replace("'", "''") in script or "opencode-favicon.ico" in script


def test_fr9211_build_and_pack_stage_opencode_favicon():
    build = _t(SCRIPTS / "Build-BobWorker.ps1")
    assert "opencode-favicon.ico" in build
    assert "FR #9211" in build
    pack = _t(REPO / "common" / "scripts" / "Pack-BobiverseRelease.ps1")
    assert "opencode-favicon.ico" in pack
    assert "assets\\opencode-favicon.ico" in pack or "assets/opencode-favicon.ico" in pack


def test_fr9211_source_icons_exist():
    tray = ROOT / "tray" / "assets"
    assert (tray / "bob-systray.ico").is_file()
    assert (tray / "opencode-favicon.ico").is_file()
    assert (REPO / "jeeves" / "assets" / "jeeves-butler.ico").is_file()
