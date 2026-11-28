"""OpenCode start matches Grok and Cursor: gh auth status does not stop the seat."""
from repo_layout import ROOT

SRC = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")


def test_opencode_start_does_not_exit_on_gh_auth():
    assert "fingerprint opencode_gh_auth_missing" not in SRC
    assert 'self.shutdown("gh-auth-missing", EXIT_REFUSED)' not in SRC
