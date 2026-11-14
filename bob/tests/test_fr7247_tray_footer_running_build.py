"""FR #7247: footer SHA is the running tray build, not a stale install-root MANIFEST."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from repo_layout import REPO

SCRIPTS = REPO / "bob" / "scripts"
COMMON_CS = REPO / "bob" / "tray" / "dialogs" / "BobDialogsCommon.cs"
WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = REPO / "bob" / "docs" / "bob-tray-dialogs.md"
WRITE = SCRIPTS / "Write-BobTrayDeployedIdentity.ps1"

EXE_FULL = "2638ab5e0123456789abcdef0123456789abcdef"
EXE_SHORT = "2638ab5"
SCR_FULL = "47465810123456789abcdef0123456789abcde"
SCR_SHORT = "4746581"


def _mod():
    sys.path.insert(0, str(SCRIPTS))
    import bob_tray_version as m  # noqa: WPS433

    return m


def test_fr7247_ci_tools_manifest_beats_stale_root(tmp_path: Path):
    """MarchHare class: root MANIFEST is 4746581, CI artifact MANIFEST sits in tools\\."""
    m = _mod()
    (tmp_path / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"source_commit": SCR_FULL}) + "\n", encoding="utf-8"
    )
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "MANIFEST.json").write_text(
        json.dumps({"source_commit": EXE_FULL, "product": "bob-tray"}) + "\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    assert m.read_exe_source_sha(tmp_path) == EXE_SHORT
    assert m.read_scripts_source_sha(tmp_path) == SCR_SHORT
    assert m.product_version_label(tmp_path, env=env) == (
        f"bob 2.0.0 (exe {EXE_SHORT} / scripts {SCR_SHORT})"
    )


def test_fr7247_matching_shas_collapse(tmp_path: Path):
    m = _mod()
    (tmp_path / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"source_commit": EXE_FULL}) + "\n", encoding="utf-8"
    )
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "MANIFEST.json").write_text(
        json.dumps({"source_commit": EXE_FULL}) + "\n", encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    assert m.product_version_label(tmp_path, env=env) == f"bob 2.0.0 ({EXE_SHORT})"


def test_fr7247_ci_stage_folder_is_exe_identity(tmp_path: Path):
    """Artifact zip root = exes + MANIFEST.json (same as tools\\ after copy)."""
    m = _mod()
    stage = tmp_path / "bob-tray-artifact"
    stage.mkdir()
    (stage / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    (stage / "bob-tray.exe").write_bytes(b"MZ")
    (stage / "MANIFEST.json").write_text(
        json.dumps({"source_commit": EXE_FULL}) + "\n", encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if k != "BOBIVERSE_BOB_VERSION"}
    # Copied into install\\tools: rename the stage folder to tools under an install root.
    inst = tmp_path / "bob"
    inst.mkdir()
    (inst / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    tools = inst / "tools"
    stage.rename(tools)
    assert m.product_version_label(inst, env=env) == f"bob 2.0.0 ({EXE_SHORT})"


def test_fr7247_readers_and_docs_name_tools_manifest():
    cs = COMMON_CS.read_text(encoding="utf-8-sig")
    assert "ExeSourceShortSha" in cs
    assert "ScriptsSourceShortSha" in cs
    assert 'Path.Combine(tools, "MANIFEST.json")' in cs
    watch = WATCH.read_text(encoding="utf-8-sig")
    assert "exe {0} / scripts {1}" in watch or "exe {0} / scripts" in watch
    writer = WRITE.read_text(encoding="utf-8")
    assert "tools" in writer and "MANIFEST.json" in writer
    docs = DOCS.read_text(encoding="utf-8")
    assert "FR #7247" in docs
    assert "tools\\MANIFEST.json" in docs or "tools/MANIFEST.json" in docs
    assert "exe" in docs.lower() and "scripts" in docs.lower()
    assert "Slab CI tray hotpatch" in docs
