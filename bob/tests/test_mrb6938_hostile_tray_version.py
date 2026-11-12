"""MRB #6938 hostile pins for FR #6924 tray MSI+SHA label."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CS = REPO / "tray" / "dialogs" / "BobDialogsCommon.cs"
ABOUT = REPO / "tray" / "dialogs" / "BobAbout.cs"
STATUS = REPO / "tray" / "dialogs" / "BobStatus.cs"
DOCS = REPO / "docs" / "bob-tray-dialogs.md"
WF = REPO.parent / ".github" / "workflows" / "build-bob-tray.yml"


def test_mrb6938_bobversion_not_cached_and_shown_rereads():
    cs = CS.read_text(encoding="utf-8-sig")
    assert "static string _bobVersion" not in cs
    assert "DeployedSourceShortSha" in cs
    about = ABOUT.read_text(encoding="utf-8-sig")
    status = STATUS.read_text(encoding="utf-8-sig")
    assert "Shown" in about
    assert "Shown" in status
    assert "BobVersion(root)" in about and "BobVersion(root)" in status


def test_mrb6938_docs_and_workflow_no_secrets():
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #6924" in docs
    assert "FR #1565" in docs
    wf = WF.read_text(encoding="utf-8")
    assert "permissions:" in wf and "contents: read" in wf
    assert "persist-credentials: false" in wf
    assert "secrets." not in wf.lower()
    assert not docs.startswith("\ufeff")
