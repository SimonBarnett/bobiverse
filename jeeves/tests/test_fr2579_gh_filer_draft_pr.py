"""FR #2579: GhCliFiler.create_draft_pr is real; harvest process_intake does not queue."""
from __future__ import annotations

import sys
from typing import Any

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import gh_filer  # noqa: E402
import intake  # noqa: E402


class _ApiStubFiler(gh_filer.GhCliFiler):
    """Real GhCliFiler.create_draft_pr path with stubbed ``_api`` (no live GitHub)."""

    def __init__(self) -> None:
        self.gh_bin = "gh"
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self._n = 0

    def _api(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int = 120,
    ) -> Any:
        self.calls.append((method.upper(), path, payload))
        m = method.upper()
        if m == "GET" and path.startswith("repos/") and "/git/" not in path and path.count("/") == 2:
            return {"default_branch": "main"}
        if m == "GET" and "/git/ref/heads/" in path:
            return {"object": {"sha": "basecommitsha"}}
        if m == "GET" and "/git/commits/" in path:
            return {"tree": {"sha": "basetreesha"}}
        if m == "POST" and path.endswith("/git/blobs"):
            self._n += 1
            return {"sha": f"blob{self._n}"}
        if m == "POST" and path.endswith("/git/trees"):
            return {"sha": "newtreesha"}
        if m == "POST" and path.endswith("/git/commits"):
            return {"sha": "newcommitsha"}
        if m == "POST" and path.endswith("/git/refs"):
            return {"ref": (payload or {}).get("ref")}
        if m == "PATCH" and "/git/refs/heads/" in path:
            return {"ref": path}
        if m == "POST" and path.endswith("/pulls"):
            assert payload and payload.get("draft") is True
            return {
                "number": 4242,
                "html_url": "https://github.com/SimonBarnett/bobiverse/pull/4242",
            }
        if m == "POST" and "/issues/" in path and path.endswith("/labels"):
            return []
        raise AssertionError(f"unexpected api {m} {path}")


def test_ghcli_create_draft_pr_builds_branch_and_draft():
    f = _ApiStubFiler()
    out = f.create_draft_pr(
        "SimonBarnett/bobiverse",
        "harvest: lesson",
        "Session summary:\nok\n",
        "intake/in_test2579",
        [{"path": "docs/skills/x.md", "content": "# x\n"}],
        ["skill", "via-intake"],
    )
    assert out["number"] == 4242
    assert out["branch"] == "intake/in_test2579"
    assert "pull/4242" in out["url"]
    assert any(c[0] == "POST" and c[1].endswith("/pulls") for c in f.calls)
    assert any("/git/blobs" in c[1] for c in f.calls)
    assert any(c[0] == "POST" and c[1].endswith("/labels") for c in f.calls)


def test_ghcli_create_draft_pr_empty_files_writes_placeholder():
    f = _ApiStubFiler()
    out = f.create_draft_pr(
        "SimonBarnett/bobiverse",
        "harvest: empty files",
        "body only",
        "intake/in_empty",
        [],
        [],
    )
    assert out["number"] == 4242
    tree_payload = next(c[2] for c in f.calls if c[0] == "POST" and c[1].endswith("/git/trees"))
    paths = [t["path"] for t in tree_payload["tree"]]
    assert any(p.startswith("docs/intake-harvest/") and p.endswith(".md") for p in paths)


def test_process_intake_harvest_uses_real_ghcli_draft_not_queue(tmp_path):
    """FR #2579: process_intake(kind=harvest) with GhCliFiler calls create_draft_pr, no queue."""
    home = tmp_path / "home"
    home.mkdir()
    filer = _ApiStubFiler()
    assert isinstance(filer, gh_filer.GhCliFiler)
    assert not isinstance(filer, intake.FakeGitHubFiler)

    payload = {
        "kind": "harvest",
        "repo": "SimonBarnett/bobiverse",
        "title": "harvest: fr2579 draft pr",
        "body": "Session summary:\nlesson\n",
        "files": [{"path": "docs/skills/fr2579.md", "content": "# lesson\n"}],
        "source": {
            "machine": "marchhare",
            "agent": "Invoke-BobiverseHarvest",
            "skill_book": "harvest",
            "version": "",
        },
        "idempotency_key": "hv-fr2579-1",
        "contact": "",
        "contact_public": False,
    }
    result = intake.process_intake(home, payload, filer=filer)
    assert result.status == 202
    assert result.body.get("queued") is False
    assert result.body.get("url")
    assert "4242" in str(result.body.get("url"))
    assert "queued_github_down" not in result.log_safe
    assert any(c[0] == "POST" and c[1].endswith("/pulls") for c in filer.calls)
    outbox = home / "intake" / "outbox"
    assert not outbox.exists() or not list(outbox.glob("*.json"))


def test_process_intake_harvest_stub_logs_draft_pr_unsupported(tmp_path):
    """FR #2579 expected #2: unsupported draft PR must not announce github_down."""

    class StubFiler(gh_filer.GhCliFiler):
        def __init__(self) -> None:
            self.gh_bin = "gh"

        def create_draft_pr(self, *a, **k):
            raise RuntimeError("gh_filer: draft PR not implemented; use issue fallback")

    home = tmp_path / "home2"
    home.mkdir()
    payload = {
        "kind": "harvest",
        "repo": "SimonBarnett/bobiverse",
        "title": "harvest: stub still",
        "body": "Session summary:\nx\n",
        "files": [],
        "source": {"machine": "x", "agent": "a", "skill_book": "harvest", "version": ""},
        "idempotency_key": "hv-fr2579-stub",
        "contact": "",
        "contact_public": False,
    }
    result = intake.process_intake(home, payload, filer=StubFiler())
    assert result.status == 202
    assert result.body.get("queued") is True
    assert "queued_draft_pr_unsupported" in result.log_safe
    assert "queued_github_down" not in result.log_safe
