"""FR #7181: worker digest POST retries 403, logs responder/ray, surfaces unhealthy."""
from __future__ import annotations

import io
import json
import urllib.error
from email.message import EmailMessage

import bob_worker as bw


def _http_error(code=403, *, server="cloudflare", ray="7181deadbeef-LHR", reason="Forbidden"):
    hdrs = EmailMessage()
    if server:
        hdrs["Server"] = server
    if ray:
        hdrs["CF-Ray"] = ray
    return urllib.error.HTTPError(
        "https://bob.ntsa.uk/bob/v1/report",
        int(code),
        reason,
        hdrs,
        io.BytesIO(b""),
    )


class _Ok:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fr7181_classify_cloudflare_vs_iis():
    cf = bw.classify_digest_http_failure(_http_error(403))
    assert cf["status"] == 403
    assert cf["responder"] == "cloudflare"
    assert cf["ray"] == "7181deadbeef-LHR"
    iis = bw.classify_digest_http_failure(
        _http_error(403, server="Microsoft-IIS/10.0", ray="")
    )
    assert iis["responder"] == "iis"
    assert not iis.get("ray")


def test_fr7181_403_then_200_retries_and_logs(monkeypatch):
    logs: list[str] = []
    n = {"i": 0}

    def fake_urlopen(req, timeout=None):
        n["i"] += 1
        assert req.get_header("User-agent") or req.get_header("User-Agent")
        if n["i"] == 1:
            raise _http_error()
        return _Ok()

    monkeypatch.setattr(bw.urllib.request, "urlopen", fake_urlopen)
    sleeps: list[float] = []
    ok = bw._http_post_json(
        "https://bob.ntsa.uk/bob/v1/report",
        {"id": "redqueen", "pid": 11844, "kind": "grok"},
        log=logs.append,
        sleep=sleeps.append,
    )
    assert ok is True
    assert n["i"] == 2
    assert sleeps and sleeps[0] > 0
    blob = " ".join(logs)
    assert "403" in blob
    assert "cloudflare" in blob.lower()
    assert "7181deadbeef-LHR" in blob
    assert "FAKE_" not in blob


def test_fr7181_persistent_403_posts_unhealthy(monkeypatch):
    payloads: list[dict] = []
    n = {"i": 0}

    def fake_urlopen(req, timeout=None):
        n["i"] += 1
        body = req.data.decode("utf-8") if isinstance(req.data, (bytes, bytearray)) else ""
        payloads.append(json.loads(body) if body else {})
        if n["i"] <= 3:
            raise _http_error()
        return _Ok()

    monkeypatch.setattr(bw.urllib.request, "urlopen", fake_urlopen)
    ok = bw.post_digest_seat_kind(
        machine="redqueen",
        pid=11844,
        nick="redqueen-11844",
        kind="grok",
        log=lambda m: None,
        sleep=lambda s: None,
    )
    assert ok is True
    last = payloads[-1]
    assert last.get("state") == "unhealthy"
    assert "403" in str(last.get("error") or "")
    assert last.get("id") == "redqueen"
    assert last.get("nick") == "redqueen-11844"
    assert last.get("pid") == 11844


def test_fr7181_docs_and_system_path(tmp_path, monkeypatch):
    from repo_layout import ROOT

    monkeypatch.setenv("USERNAME", "SYSTEM")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "systemprofile"))
    docs = (ROOT / "bob" / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "FR #7181" in docs
    assert "CF-Ray" in docs or "cf-ray" in docs.lower()
    assert "unhealthy" in docs.lower()
