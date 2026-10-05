"""FR #2411: crash_report redact, signature, spool, dedupe, install hooks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import crash_report as cr  # noqa: E402


class FakeFiler:
    def __init__(self):
        self.created = []
        self.comments = []

    def create_issue(self, repo, title, body, labels):
        n = 1000 + len(self.created)
        self.created.append({"repo": repo, "title": title, "body": body, "labels": labels, "number": n})
        return {"number": n, "url": f"https://github.com/{repo}/issues/{n}"}

    def comment_issue(self, repo, number, body):
        self.comments.append({"repo": repo, "number": number, "body": body})


def test_redact_secrets():
    text = "GH_TOKEN=ghp_secret123\npassword: hunter2\nxai_api_key=abc"
    out = cr.redact(text)
    assert "ghp_secret123" not in out
    assert "hunter2" not in out
    assert "abc" not in out
    assert "<redacted>" in out


def test_signature_stable(tmp_path):
    try:
        raise ValueError("boom GH_TOKEN=nope")
    except ValueError as e:
        import traceback
        tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        a = cr.traceback_signature(type(e), e, tb)
        b = cr.traceback_signature(type(e), e, tb)
    assert a == b
    assert len(a) == 16
    assert "nope" not in a


def test_spool_when_filer_fails(tmp_path, monkeypatch):
    spool = tmp_path / "spool"
    class Boom:
        def create_issue(self, *a, **k):
            raise RuntimeError("offline")

    try:
        raise RuntimeError("explode")
    except RuntimeError:
        import sys as _sys
        et, ev, tb = _sys.exc_info()
        r = cr.report_exception(et, ev, tb, filer=Boom(), spool=spool, search=lambda *a, **k: [])
    assert r["action"] == "spool"
    files = list(spool.glob("crash-*.json"))
    assert len(files) == 1
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert "crash-sig:" in doc["body"]
    assert "explode" in doc["body"]


def test_dedupe_comments_instead_of_create(tmp_path):
    filer = FakeFiler()
    try:
        raise KeyError("dup")
    except KeyError:
        import sys as _sys
        et, ev, tb = _sys.exc_info()
        sig = cr.traceback_signature(et, ev, "".join(__import__("traceback").format_exception(et, ev, tb)))

        def search(repo, marker):
            return [{"number": 42, "body": f"<!-- crash-sig:{sig} -->", "title": "x"}]

        r = cr.report_exception(et, ev, tb, filer=filer, search=search, spool=tmp_path)
    assert r["action"] == "comment"
    assert r["number"] == 42
    assert filer.created == []
    assert len(filer.comments) == 1


def test_create_issue_happy(tmp_path):
    filer = FakeFiler()
    try:
        raise RuntimeError("fresh")
    except RuntimeError:
        import sys as _sys
        et, ev, tb = _sys.exc_info()
        r = cr.report_exception(et, ev, tb, filer=filer, search=lambda *a, **k: [], spool=tmp_path)
    assert r["action"] == "create"
    assert r["number"] >= 1000
    assert "crash-auto" in filer.created[0]["labels"]


def test_flush_spool(tmp_path):
    filer = FakeFiler()
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / "crash-1.json").write_text(
        json.dumps({
            "sig": "abcd1234abcd1234",
            "title": "crash test",
            "body": "<!-- crash-sig:abcd1234abcd1234 -->\nhello",
            "repo": "SimonBarnett/bobiverse",
        }),
        encoding="utf-8",
    )
    done = cr.flush_spool(filer=filer, spool=spool, search=lambda *a, **k: [])
    assert done and done[0]["ok"]
    assert not list(spool.glob("crash-*.json"))


def test_install_hooks():
    cr._reset_for_tests()
    assert cr.install(flush=False, product="test") is True
    assert cr.is_installed()
    assert cr.install(flush=False) is False  # once
    assert sys.excepthook is not sys.__excepthook__
