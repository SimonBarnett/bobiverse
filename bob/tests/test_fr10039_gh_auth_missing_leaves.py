"""FR #10039: gh_auth_missing shuts the seat down. It does not look ready."""
from repo_layout import ROOT

SRC = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")


def test_fr10039_blocked_auth_shuts_down():
    mark = SRC.index("fingerprint opencode_gh_auth_missing")
    body = SRC[mark - 200:mark + 500]
    assert "FR #10039" in body
    assert 'self.shutdown("gh-auth-missing", EXIT_REFUSED)' in body
