"""FR #3117: intake_allowlist monitor detects live repo_not_allowed drift."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))

import intake_allowlist as ial  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
INTAKE_PY = REPO / "common" / "scripts" / "intake.py"


class _FakeResp:
    def __init__(self, status: int, body: dict):
        self.status = status
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_required_repos_include_a_search_and_trutex():
    req = ial.REQUIRED_ALLOW_REPOS
    assert "SimonBarnett/a-search" in req
    assert "SimonBarnett/trutex" in req
    assert "SimonBarnett/bobiverse" in req


def test_parse_default_allow_repos_from_source():
    text = INTAKE_PY.read_text(encoding="utf-8-sig")
    got = ial.parse_default_allow_repos(text)
    for repo in ial.REQUIRED_ALLOW_REPOS:
        assert repo in got, repo


def test_finding_when_live_rejects_a_search(monkeypatch):
    monkeypatch.setenv("BOB_INTAKE_URL", "https://example.test/bob/v1/intake")
    monkeypatch.setenv(
        "BOB_INTAKE_REQUIRED_REPOS",
        "SimonBarnett/bobiverse,SimonBarnett/a-search",
    )
    monkeypatch.setenv("BOB_INTAKE_PY", str(INTAKE_PY))

    def opener(req, timeout=20.0):
        payload = json.loads(req.data.decode("utf-8"))
        repo = payload["repo"]
        if repo.endswith("/a-search"):
            raise HTTPError(
                req.full_url,
                403,
                "Forbidden",
                hdrs=None,
                fp=io.BytesIO(b'{"error":"repo_not_allowed"}'),
            )
        return _FakeResp(202, {"intake_id": "in_test", "queued": False})

    args = type("A", (), {"chair_home": "", "digest_home": "", "dry_run": False})()
    payload, code = ial.check(args, opener=opener)
    assert code == 1, payload
    assert payload["ok"] is False
    assert any("a-search" in f for f in payload["findings"])
    assert payload["source_ok"] is True


def test_ok_when_all_required_allowed(monkeypatch):
    monkeypatch.setenv("BOB_INTAKE_URL", "https://example.test/bob/v1/intake")
    monkeypatch.setenv(
        "BOB_INTAKE_REQUIRED_REPOS",
        "SimonBarnett/bobiverse,SimonBarnett/a-search",
    )
    monkeypatch.setenv("BOB_INTAKE_PY", str(INTAKE_PY))

    def opener(req, timeout=20.0):
        return _FakeResp(202, {"intake_id": "in_ok", "queued": False})

    args = type("A", (), {"chair_home": "", "digest_home": "", "dry_run": False})()
    payload, code = ial.check(args, opener=opener)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["findings"] == []


def test_source_missing_repo_allowed_is_finding(tmp_path, monkeypatch):
    """FR #3135: source without repo_allowed / SimonBarnett gate is a finding."""
    monkeypatch.setenv("BOB_INTAKE_URL", "https://example.test/bob/v1/intake")
    monkeypatch.setenv("BOB_INTAKE_REQUIRED_REPOS", "SimonBarnett/a-search")
    bad = tmp_path / "intake.py"
    bad.write_text(
        'DEFAULT_ALLOW_REPOS = frozenset({"SimonBarnett/bobiverse"})\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_INTAKE_PY", str(bad))

    def opener(req, timeout=20.0):
        return _FakeResp(202, {"intake_id": "in_ok", "queued": False})

    args = type("A", (), {"chair_home": "", "digest_home": "", "dry_run": False})()
    payload, code = ial.check(args, opener=opener)
    assert code == 1, payload
    assert payload["source_ok"] is False
    assert any(
        "repo_allowed" in f or "DEFAULT_ALLOW_REPOS missing" in f or "SimonBarnett" in f
        for f in payload["findings"]
    )


def test_cloudflare_1010_is_probe_error_not_allowlist_drift(monkeypatch):
    """FR #8861: bare CF 403 must not become Sync/compose repo_not_allowed."""
    monkeypatch.setenv("BOB_INTAKE_URL", "https://example.test/bob/v1/intake")
    monkeypatch.setenv("BOB_INTAKE_REQUIRED_REPOS", "SimonBarnett/bobiverse")
    monkeypatch.setenv("BOB_INTAKE_PY", str(INTAKE_PY))

    def opener(req, timeout=20.0):
        assert req.get_header("User-agent") or req.headers.get("User-agent")
        raise HTTPError(
            req.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(b"error code: 1010\n"),
        )

    args = type("A", (), {"chair_home": "", "digest_home": "", "dry_run": False})()
    payload, code = ial.check(args, opener=opener)
    assert code == 1, payload
    assert payload["source_ok"] is True
    assert any("probe error" in f and "1010" in f for f in payload["findings"])
    assert not any("Sync/compose" in f for f in payload["findings"])


def test_probe_sets_user_agent(monkeypatch):
    seen = {}

    def opener(req, timeout=20.0):
        seen["ua"] = req.get_header("User-agent") or req.headers.get("User-agent")
        return _FakeResp(202, {"intake_id": "in_ok", "queued": False})

    monkeypatch.setenv("BOB_INTAKE_URL", "https://example.test/bob/v1/intake")
    monkeypatch.setenv("BOB_INTAKE_REQUIRED_REPOS", "SimonBarnett/bobiverse")
    monkeypatch.setenv("BOB_INTAKE_PY", str(INTAKE_PY))
    args = type("A", (), {"chair_home": "", "digest_home": "", "dry_run": False})()
    payload, code = ial.check(args, opener=opener)
    assert code == 0, payload
    assert seen.get("ua") and "BobiverseIntakeAllowlist" in seen["ua"]


def test_dry_run_via_main(monkeypatch):
    rc = ial.main(["--dry-run"])
    assert rc == 0
