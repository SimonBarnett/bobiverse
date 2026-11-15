"""FR #7547: build-jeeves runs jeeves/tests pytest before PyInstaller."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

WF = REPO / ".github" / "workflows" / "build-jeeves.yml"


def _steps(text: str) -> list[str]:
    """Ordered step name lines from the workflow."""
    names: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- name:"):
            names.append(s[len("- name:") :].strip())
    return names


def test_fr7547_build_jeeves_runs_pytest_before_build():
    assert WF.is_file()
    text = WF.read_text(encoding="utf-8")
    assert "FR #7547" in text or "7547" in text
    assert "pytest" in text.lower()
    assert "jeeves/tests" in text or r"jeeves\tests" in text
    assert "python -m pytest" in text
    names = _steps(text)
    pytest_i = next(i for i, n in enumerate(names) if "pytest" in n.lower() and "jeeves" in n.lower())
    build_i = next(i for i, n in enumerate(names) if "Build-Jeeves" in n or "Build jeeves" in n)
    assert pytest_i < build_i, (names, pytest_i, build_i)
    # Failing suite must fail the job (no soft-skip).
    assert "throw" in text and "pytest exit" in text
    assert "test_fr7547_build_jeeves_pytest.py" in text


def test_fr7547_fr7527_login_test_is_under_jeeves_tests():
    """Acceptance probe: breaking this file must fail build-jeeves once the suite runs."""
    path = REPO / "jeeves" / "tests" / "test_fr7527_login_no_bare_404.py"
    assert path.is_file()
