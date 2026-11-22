"""FR #7517: webhooks kit ships favicon and jeeves/assets; CI fails on missing refs."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import REPO

import jeeves_webhooks_ci as kit

PS = shutil.which("powershell") or shutil.which("pwsh")
NEED_PS = pytest.mark.skipif(not PS, reason="powershell or pwsh required")
WEB = REPO / ".github" / "workflows" / "build-jeeves-webhooks.yml"


def _build_kit(tmp_path: Path) -> Path:
    out = tmp_path / "kit"
    www = REPO / "jeeves" / "www" / "irc-ntsa"
    installer = REPO / "jeeves" / "scripts" / "Install-BobWebhooks.ps1"
    kit.write_site_kit(www, installer, out, "test-fr7517", repo=REPO)
    return out


def test_fr7517_kit_assets_table_paths_exist():
    assert len(kit.KIT_ASSETS) == 3
    for src, kit_rel, url in kit.KIT_ASSETS:
        assert (REPO / src).is_file(), src
        assert kit_rel.startswith(("www/", "assets/"))
        assert url.startswith("/")


def test_fr7517_write_site_kit_includes_assets_and_hashes(tmp_path: Path):
    out = _build_kit(tmp_path)
    data = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    by_path = {e["path"]: e["sha256"] for e in data["files"]}
    assert len(data["files"]) == 23
    for src, kit_rel, _url in kit.KIT_ASSETS:
        assert kit_rel in by_path
        digest = hashlib.sha256((out / kit_rel).read_bytes()).hexdigest()
        assert digest == by_path[kit_rel]
        assert digest == hashlib.sha256((REPO / src).read_bytes()).hexdigest()
    kit.verify_site_kit(out)


def test_fr7517_verify_fails_when_logo_deleted(tmp_path: Path):
    out = _build_kit(tmp_path)
    (out / "assets" / "ntsa-gut-logo.png").unlink()
    with pytest.raises(SystemExit, match="ntsa-gut-logo.png"):
        kit.verify_site_kit(out)


def test_fr7517_verify_fails_when_favicon_deleted(tmp_path: Path):
    out = _build_kit(tmp_path)
    (out / "www" / "favicon.ico").unlink()
    with pytest.raises(SystemExit, match="favicon.ico"):
        kit.verify_site_kit(out)


def test_fr7517_verify_fails_on_hash_mismatch(tmp_path: Path):
    out = _build_kit(tmp_path)
    fav = out / "www" / "favicon.ico"
    fav.write_bytes(fav.read_bytes() + b"\x00")
    with pytest.raises(SystemExit, match="hash mismatch"):
        kit.verify_site_kit(out)


def test_fr7517_strict_smoke_fails_missing_asset(tmp_path: Path):
    root = tmp_path / "pub"
    root.mkdir()
    (root / "index.html").write_text(
        '<html><img src="/jeeves/assets/x.png"></html>',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="missing linked asset"):
        kit.smoke_serve(root, strict=True)


def test_fr7517_strict_smoke_allowlists_dynamic_routes(tmp_path: Path):
    root = tmp_path / "pub"
    root.mkdir()
    (root / "index.html").write_text(
        '<html><a href="/jeeves/login">login</a>'
        '<a href="/bob/v1/report">report</a></html>',
        encoding="utf-8",
    )
    kit.smoke_serve(root, strict=True)


def test_fr7517_workflow_filters_include_assets_and_test():
    hooks = kit.workflow_paths(WEB.read_text(encoding="utf-8"), "pull_request")
    assert "jeeves/assets/**" in hooks
    assert "bob/tray/assets/ntsa-gut-logo.png" in hooks
    assert "jeeves/tests/test_fr7517_webhooks_kit_assets.py" in hooks
    assert kit.workflow_runs(hooks, ["jeeves/assets/jeeves-butler.ico"])
    assert kit.workflow_runs(hooks, ["bob/tray/assets/ntsa-gut-logo.png"])
    text = WEB.read_text(encoding="utf-8")
    assert "test_fr7517_webhooks_kit_assets.py" in text


@NEED_PS
def test_fr7517_clean_kit_install_publishes_assets(tmp_path: Path):
    kit_dir = _build_kit(tmp_path / "built")
    # Isolated copy outside any checkout path resolution
    isolated = tmp_path / "isolated-kit"
    shutil.copytree(kit_dir, isolated)
    physical = tmp_path / "published"
    physical.mkdir()
    proc = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-File",
            str(isolated / "Install-BobWebhooks.ps1"),
            "-SiteKit",
            "-PhysicalPath",
            str(physical),
            "-Backend",
            "http://127.0.0.1:7700",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for _src, kit_rel, url in kit.KIT_ASSETS:
        pub = physical / kit.published_path_for_url(url)
        assert pub.is_file(), url
        assert pub.read_bytes() == (isolated / kit_rel).read_bytes()
    kit.smoke_serve(physical, strict=True)
    kit._assert_published_kit_assets(physical, isolated)
