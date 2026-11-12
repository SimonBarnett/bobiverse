"""FR #6755: GET /queue HTML waiting / in-progress lists."""
from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import jeeves_settings_http as http


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _queue(home: Path, *, accepted=None, unaccepted=None):
    home.mkdir(parents=True, exist_ok=True)
    doc = {
        "unaccepted": list(unaccepted or []),
        "accepted": list(accepted or []),
        "done": [],
    }
    (home / "queue.json").write_text(json.dumps(doc), encoding="utf-8")


def _start(tmp_path, monkeypatch, *, unaccepted=None, accepted=None):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(digest, unaccepted=unaccepted, accepted=accepted)
    port = _free_port()
    srv = http.start_settings_http(
        chair,
        bind="127.0.0.1",
        port=port,
        digest_home=digest,
        authenticator=lambda u, p, d="": u == "ApplianceAdmin" and p == "FAKE_ok",
    )
    assert srv is not None
    base = f"http://127.0.0.1:{port}"
    return srv, base


def _login(base: str) -> dict[str, str]:
    login = urllib.request.Request(
        base + "/api/login",
        data=json.dumps(
            {"username": "ApplianceAdmin", "password": "FAKE_ok"}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(login, timeout=5) as resp:
        tok = json.loads(resp.read().decode("utf-8"))["session_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_fr6755_queue_page_unauth_is_login(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch)
    try:
        req = urllib.request.Request(base + "/queue", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
        assert "login" in html.lower()
        assert "Nothing is waiting." not in html
        assert "Sign in" in html or "password" in html.lower()
    finally:
        http.stop_settings_http(srv)


def test_fr6755_queue_page_empty_copy(tmp_path, monkeypatch):
    srv, base = _start(tmp_path, monkeypatch, unaccepted=[], accepted=[])
    try:
        hdr = _login(base)
        req = urllib.request.Request(base + "/queue", headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
        assert "Nothing is waiting." in html
        assert "Nothing is in progress." in html
    finally:
        http.stop_settings_http(srv)


def test_fr6755_queue_page_one_waiting_zero_accepted(tmp_path, monkeypatch):
    srv, base = _start(
        tmp_path,
        monkeypatch,
        unaccepted=[
            {
                "task": "FR",
                "repo": "SimonBarnett/bobiverse",
                "id": "#6755",
                "worker": "flamingo-1",
                "token": "ghs_FAKE_QUEUE_PAGE_DROP",
                "body": "password=should-not-leak",
            }
        ],
        accepted=[],
    )
    try:
        hdr = _login(base)
        req = urllib.request.Request(base + "/queue", headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
        assert "SimonBarnett/bobiverse" in html
        assert "FR" in html
        assert "#6755" in html
        assert "flamingo-1" in html
        assert "Nothing is in progress." in html
        assert "Nothing is waiting." not in html
        assert "ghs_FAKE" not in html
        assert "MUST" not in html or "QUEUE_PAGE_DROP" not in html
        assert "password=" not in html.lower()
        req = urllib.request.Request(base + "/", headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            settings = resp.read().decode("utf-8")
        assert 'href="/queue"' in settings
    finally:
        http.stop_settings_http(srv)


def test_fr6755_docs_name_queue_page():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "/queue" in doc
    assert "FR #6755" in doc
