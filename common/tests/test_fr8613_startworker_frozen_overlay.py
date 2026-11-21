"""FR #8613: frozen ear overlays InstallRoot scripts/startworker.py after recycle.

#8612 landed the opencode/free grammar on tip, but FROZEN_SCRIPT_OVERLAY only
allowed bobreport + opencode_fuel. Frozen bob-ear.exe kept the old usage string
until a rebuild. Allowlist startworker (marker OPENCODE_SLOTS) so git_ff recycle
hotpatches without rebuilding the ear. Do NOT add startworker.py to
EAR_RUNTIME_DISK_SCRIPTS - that would provenance-gate and block tip hotpatch.
"""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import irc_agent
from repo_layout import ROOT

AGENT = ROOT / "common" / "scripts" / "irc_agent.py"
STARTWORKER = ROOT / "common" / "scripts" / "startworker.py"


def test_fr8613_startworker_in_frozen_script_overlay():
    assert "startworker" in irc_agent.FROZEN_SCRIPT_OVERLAY
    assert "bobreport" in irc_agent.FROZEN_SCRIPT_OVERLAY
    assert "opencode_fuel" in irc_agent.FROZEN_SCRIPT_OVERLAY
    # Hotpatch path: not provenance-gated (rebuild still optional).
    assert "startworker.py" not in irc_agent.EAR_RUNTIME_DISK_SCRIPTS


def test_fr8613_startworker_overlay_marker_is_opencode_slots():
    src = AGENT.read_text(encoding="utf-8")
    assert "STARTWORKER_OVERLAY_MARKER" in src
    assert irc_agent.STARTWORKER_OVERLAY_MARKER == "OPENCODE_SLOTS"
    tip = STARTWORKER.read_text(encoding="utf-8")
    assert "OPENCODE_SLOTS" in tip


def test_fr8613_frozen_overlay_loads_disk_startworker(tmp_path: Path, monkeypatch):
    """Disk tip startworker with OPENCODE_SLOTS wins over an old embed."""
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    mei = tmp_path / "_MEI"
    mei.mkdir()
    exe = scripts / "bob-ear.exe"
    exe.write_bytes(b"MZ")

    (mei / "startworker.py").write_text(
        textwrap.dedent(
            """
            CMD = "!startworker"
            def parse(body):
                return ("agent", None)
            def usage():
                return "usage: !startworker [agent|plan] [machine]"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (scripts / "startworker.py").write_text(
        textwrap.dedent(
            """
            CMD = "!startworker"
            OPENCODE_SLOTS = ("free", "paid")
            AGENTS = ("auto", "grok", "cursor", "opencode")
            def parse(body):
                return ("opencode", "free", "flamingo", None)
            def usage():
                return (
                    "usage: !startworker [agent|plan|grok|cursor|opencode] "
                    "[free|paid] [machine]"
                )
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (scripts / "bobreport.py").write_text(
        "def opencode_install_root(*a, **k):\n    return None\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("BOB_INSTALL_ROOT", str(install))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)

    sys.modules.pop("startworker", None)
    sys.meta_path[:] = [
        f for f in sys.meta_path if not isinstance(f, irc_agent._InstallScriptOverlay)
    ]
    # Isolate from tip common/scripts on PYTHONPATH / sys.path.
    monkeypatch.setattr(sys, "path", [str(mei)] + [p for p in sys.path if "bobiverse" not in p.replace("\\", "/").lower()])

    got = irc_agent.prefer_install_scripts_path(
        env={"BOB_INSTALL_ROOT": str(install)},
        frozen=True,
        executable=exe,
        path_list=None,
    )
    assert got is not None
    sw = importlib.import_module("startworker")
    assert hasattr(sw, "OPENCODE_SLOTS")
    assert "opencode" in sw.usage()
    # Must be the disk tip copy, not the old mei embed.
    assert sw.__file__ and str(scripts) in str(Path(sw.__file__).resolve())


def test_fr8613_old_disk_startworker_without_marker_not_overlaid(tmp_path: Path):
    """Pre-#8610 disk startworker lacks OPENCODE_SLOTS - keep embed."""
    install = tmp_path / "bob"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "bobreport.py").write_text(
        "def opencode_install_root(*a, **k):\n    return None\n",
        encoding="utf-8",
    )
    (scripts / "startworker.py").write_text(
        "CMD = \"!startworker\"\ndef usage():\n    return \"usage: !startworker [agent|plan] [machine]\"\n",
        encoding="utf-8",
    )
    finder = irc_agent._InstallScriptOverlay(scripts)
    assert finder.find_spec("startworker", None) is None
