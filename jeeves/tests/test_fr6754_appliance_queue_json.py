"""FR #6754: GET /api/queue whitelist (repo, task, id, worker) + LAN/session."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import jeeves_settings as js
import jeeves_settings_http as http


def _fake_ghs() -> str:
    # Runtime-assemble so source has no contiguous hunter-style secret (FR #3304).
    return "ghs_" + "FAKE_" + "QUEUE_MUST_DROP"


def _fake_password_body() -> str:
    return "pass" + "word" + "=" + "should-not-leak"


def _fake_bearer_shaped() -> str:
    # Not a real JWT; parts only (FR #3304).
    return "Bear" + "er " + "FAKE_" + "STATUS_TOKEN_EXAMPLE"



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


def test_fr6754_queue_whitelist_drops_extra_keys(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(
        digest,
        unaccepted=[
            {
                "task": "FR",
                "repo": "SimonBarnett/bobiverse",
                "id": "#6754",
                "worker": "flamingo-1",
                "token": _fake_ghs(),
                "body": _fake_password_body(),
                "offered_to": "other",
            }
        ],
        accepted=[
            {
                "task": "MRB",
                "repo": "a/b",
                "id": "#9",
                "nick": "redqueen-2",
                "gh_token": _fake_bearer_shaped(),
                "accepted_by": "redqueen-2",
            }
        ],
    )
    view = js.api_get_queue(chair, digest_home=digest, client_ip="10.0.0.2")
    assert view["ok"] is True
    assert list(view.keys()) == ["ok", "unaccepted", "accepted"] or set(
        view.keys()
    ) >= {"ok", "unaccepted", "accepted"}
    (u,) = view["unaccepted"]
    assert u == {
        "repo": "SimonBarnett/bobiverse",
        "task": "FR",
        "id": "#6754",
        "worker": "flamingo-1",
    }
    (a,) = view["accepted"]
    assert a == {"repo": "a/b", "task": "MRB", "id": "#9", "worker": "redqueen-2"}
    blob = json.dumps(view)
    assert "ghs_FAKE" not in blob
    assert "MUST_DROP" not in blob
    assert ("pass" + "word" + "=") not in blob.lower()
    assert "offered_to" not in blob
    assert "accepted_by" not in blob
    assert "gh_token" not in blob


def test_fr6754_queue_worker_omitted_without_worker_or_nick(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(
        digest,
        unaccepted=[{"task": "UAT", "repo": "o/r", "id": "#0"}],
        accepted=[],
    )
    view = js.api_get_queue(chair, digest_home=digest, client_ip="127.0.0.1")
    assert view["ok"] is True
    assert view["unaccepted"] == [{"repo": "o/r", "task": "UAT", "id": "#0"}]
    assert "worker" not in view["unaccepted"][0]


def test_fr6754_empty_queue_ok_true(tmp_path):
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(digest, accepted=[], unaccepted=[])
    view = js.api_get_queue(chair, digest_home=digest, client_ip="192.168.1.8")
    assert view == {"ok": True, "unaccepted": [], "accepted": []}


def test_fr6754_queue_non_lan_forbidden(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    view = js.api_get_queue(home, client_ip="8.8.8.8")
    assert view["ok"] is False
    assert "forbidden" in view["error"]


def test_fr6754_http_queue_session_and_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP", "1")
    chair = tmp_path / "chair"
    digest = tmp_path / "digest"
    chair.mkdir()
    _queue(digest, accepted=[], unaccepted=[])
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
    try:
        unauth = urllib.request.Request(base + "/api/queue", method="GET")
        try:
            urllib.request.urlopen(unauth, timeout=5)
            raise AssertionError("expected 401 without session")
        except urllib.error.HTTPError as e:
            assert e.code == 401

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
        hdr = {"Authorization": f"Bearer {tok}"}
        req = urllib.request.Request(base + "/api/queue", headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        assert body == {"ok": True, "unaccepted": [], "accepted": []}
    finally:
        http.stop_settings_http(srv)


def test_fr6754_docs_name_queue_route():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "/api/queue" in doc
    assert "FR #6754" in doc

def test_fr6754_docs_keep_prior_appliance_paragraphs():
    root = Path(__file__).resolve().parents[2]
    doc = (root / "jeeves" / "docs" / "jeeves-settings-appliance.md").read_text(
        encoding="utf-8"
    )
    assert "/api/queue" in doc
    assert "FR #6754" in doc
    assert "Bool SCHEMA keys" in doc
    assert "FR #6750" in doc
    assert "login page has one account field" in doc
