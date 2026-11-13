"""FR #7103: GitHub-hosted Windows pytest as LocalSystem (no self-hosted runners)."""
from __future__ import annotations

from pathlib import Path

import pytest

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "pytest-localsystem.yml"
PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseLocalSystemPytest.ps1"
PY = ROOT / "common" / "scripts" / "bobiverse_localsystem_ci.py"
DOCS = ROOT / "docs" / "bobiverse-build.md"


def test_fr7103_workflow_is_github_hosted_windows_not_self_hosted():
    assert WF.is_file(), "missing .github/workflows/pytest-localsystem.yml"
    text = WF.read_text(encoding="utf-8")
    assert "name: pytest-localsystem" in text
    assert "runs-on: windows-latest" in text
    assert "runs-on: self-hosted" not in text.lower()
    assert "workflow_dispatch" in text
    assert "persist-credentials: false" in text
    assert "contents: read" in text
    assert "setup-python@v5" in text
    assert 'python-version: "3.12"' in text or "python-version: '3.12'" in text
    assert "Invoke-BobiverseLocalSystemPytest.ps1" in text
    assert "gh release create" not in text
    assert "GITHUB_TOKEN" not in text
    assert "secrets." not in text.lower()


def test_fr7103_ps1_registers_system_scheduled_task_not_psexec():
    assert PS1.is_file()
    text = PS1.read_text(encoding="utf-8")
    assert "New-ScheduledTaskPrincipal" in text
    assert "SYSTEM" in text
    assert "Register-ScheduledTask" in text
    assert "Invoke-Expression" not in text
    assert "gh release create" not in text
    assert "bobiverse_localsystem_ci.py" in text
    # MRB #7114: SYSTEM PATH has no setup-python; wrapper must use resolved python.exe.
    assert "(Get-Command python).Source" in text
    assert "__PY__" in text
    assert "& python " not in text
    assert "UTF8Encoding" in text or "UTF8Encoding $false" in text or "new UTF8Encoding" in text.lower()


def test_fr7103_python_helper_exports():
    import bobiverse_localsystem_ci as m

    names = {s["name"] for s in m.SUITE_SPECS}
    assert names == {"common", "bob", "jeeves", "airc"}
    for spec in m.SUITE_SPECS:
        assert "python -m pytest" in spec["cmd"]
        assert spec["name"] in spec["cmd"]


def test_fr7103_child_env_drops_secret_names():
    import bobiverse_localsystem_ci as m

    src = {
        "PATH": "C:\\Python312",
        "GITHUB_TOKEN": "FAKE_gha_token_value",
        "GH_TOKEN": "FAKE_gh_token_value",
        "ACTIONS_RUNTIME_TOKEN": "FAKE_runtime",
        "BOB_OK": "keep-me",
        "NPM_TOKEN": "FAKE_npm",
    }
    out = m.child_env(src)
    assert out["PATH"] == "C:\\Python312"
    assert out["BOB_OK"] == "keep-me"
    assert "GITHUB_TOKEN" not in out
    assert "GH_TOKEN" not in out
    assert "ACTIONS_RUNTIME_TOKEN" not in out
    assert "NPM_TOKEN" not in out
    joined = " ".join(out.values())
    assert "FAKE_gha_token_value" not in joined
    assert "FAKE_gh_token_value" not in joined


def test_fr7103_scrub_log_redacts_token_shapes():
    import bobiverse_localsystem_ci as m

    raw = "ok ghp_EXAMPLEPLACEHOLDERTOKEN0001 GH_TOKEN=FAKE_secret_line done"
    cleaned = m.scrub_ci_log(raw)
    assert "ghp_" not in cleaned
    assert "FAKE_secret_line" not in cleaned
    assert "REDACTED" in cleaned
    assert "ok" in cleaned and "done" in cleaned


def test_fr7103_identity_detects_localsystem():
    import bobiverse_localsystem_ci as m

    assert m.is_localsystem_identity("nt authority\\system", "SYSTEM") is True
    assert m.is_localsystem_identity("FLAMINGO\\runneradmin", "runneradmin") is False


def test_fr7103_docs_name_the_workflow():
    docs = DOCS.read_text(encoding="utf-8")
    assert "FR #7103" in docs
    assert "pytest-localsystem.yml" in docs
    assert "LocalSystem" in docs


def test_fr7103_no_release_side_effects_in_helper():
    text = PY.read_text(encoding="utf-8")
    assert "gh release" not in text
    assert "github-prerelease" not in text
