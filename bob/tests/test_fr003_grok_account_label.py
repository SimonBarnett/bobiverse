"""FR #6143 / FR-003: Publish xAI/Grok account label on digest (grok_account)."""
from __future__ import annotations

import json
import types
from pathlib import Path
from unittest import mock

import pytest

import bobreport
import irc_agent
import registered_machines

# Runtime-built fake credentials (never contiguous secret literals in source).
_FAKE_KEY = "FAKE_" + "KEY_" + ("x" * 24)
_FAKE_REFRESH = "FAKE_" + "REFRESH_" + ("y" * 32)
_FAKE_EMAIL = "alice.example@" + "xai.test"
_FAKE_OTHER = "bob.example@" + "xai.test"
_SECRET_MARKERS = ("refresh_token", "password=", "xai_api_key=", _FAKE_KEY, _FAKE_REFRESH)


def _home(tmp_path: Path, mids=None) -> Path:
    registered_machines.save_registered(tmp_path, set(mids or {"redqueen", "marchhare"}))
    return tmp_path


def _auth_doc_email(email: str = _FAKE_EMAIL, *, with_secrets: bool = True) -> dict:
    row = {
        "email": email,
        "first_name": "Alice",
        "last_name": "Example",
        "user_id": "user-fake-1",
    }
    if with_secrets:
        row["key"] = _FAKE_KEY
        row["refresh_token"] = _FAKE_REFRESH
    return {f"https://auth.x.ai::fake-client-{email.split('@')[0]}": row}


def _scan_blob(blob: object) -> None:
    text = blob if isinstance(blob, str) else json.dumps(blob, default=str)
    lower = text.lower()
    for m in _SECRET_MARKERS:
        assert m.lower() not in lower, f"secret marker leaked: {m}"


def test_reader_email_ok(tmp_path: Path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(_auth_doc_email()), encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    status, label = bobreport.read_grok_account_label()
    assert status == "ok"
    assert label == _FAKE_EMAIL
    assert label != "bob-redqueen"


def test_reader_names_when_no_email(tmp_path: Path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "https://auth.x.ai::c1": {
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                    "key": _FAKE_KEY,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    status, label = bobreport.read_grok_account_label()
    assert status == "ok"
    assert label == "Ada Lovelace"


def test_reader_skips_api_key_scope(tmp_path: Path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps({"xai::api_key": {"key": _FAKE_KEY, "email": _FAKE_EMAIL}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    status, label = bobreport.read_grok_account_label()
    assert status == "none"
    assert label is None


def test_reader_ambiguous_distinct_labels(tmp_path: Path, monkeypatch):
    doc = _auth_doc_email(_FAKE_EMAIL)
    doc.update(_auth_doc_email(_FAKE_OTHER))
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    status, label = bobreport.read_grok_account_label()
    assert status == "none"
    assert label is None


def test_reader_missing_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(tmp_path / "missing-auth.json"))
    status, label = bobreport.read_grok_account_label()
    assert status == "none"
    assert label is None


def test_reader_malformed_json(tmp_path: Path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    status, label = bobreport.read_grok_account_label()
    assert status == "unknown"
    assert label is None


def test_reader_non_object_root(tmp_path: Path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    status, label = bobreport.read_grok_account_label()
    # Contract: non-object root => none (plan design choice 6 / reader).
    assert status == "none"
    assert label is None


def test_reader_rejects_control_and_oversize(tmp_path: Path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps({"https://auth.x.ai::c": {"email": "bad\x00name@x.ai"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    status, label = bobreport.read_grok_account_label()
    assert status == "ok"
    assert "\x00" not in (label or "")

    auth.write_text(
        json.dumps({"https://auth.x.ai::c": {"email": "a" * 300 + "@x.ai"}}),
        encoding="utf-8",
    )
    status2, label2 = bobreport.read_grok_account_label()
    assert status2 == "none"
    assert label2 is None


def test_chair_merge_persist_reload_export(tmp_path: Path):
    home = _home(tmp_path)
    mid = "redqueen"
    out = bobreport.apply_callback(
        home,
        {"op": "merge", "machine": mid, "online": True, "grok_account": _FAKE_EMAIL},
    )
    assert out.ok
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("grok_account") == _FAKE_EMAIL
    assert ent.get("grok_account") != "bob-redqueen"
    exported = bobreport.export_machine_for_tray(home, mid, ent)
    assert exported.get("grok_account") == _FAKE_EMAIL
    _scan_blob(exported)
    _scan_blob(bobreport.load_digest(home))


def test_omitting_merge_keeps_label(tmp_path: Path):
    home = _home(tmp_path)
    mid = "redqueen"
    bobreport.apply_callback(
        home, {"op": "merge", "machine": mid, "grok_account": _FAKE_EMAIL}
    )
    bobreport.apply_callback(home, {"op": "merge", "machine": mid, "online": True, "weekly": 9})
    ent = bobreport.load_digest(home)["machines"][mid]
    assert ent.get("grok_account") == _FAKE_EMAIL


def test_null_and_cleared_remove_label(tmp_path: Path):
    home = _home(tmp_path)
    mid = "redqueen"
    bobreport.apply_callback(
        home, {"op": "merge", "machine": mid, "grok_account": _FAKE_EMAIL}
    )
    bobreport.apply_callback(
        home, {"op": "merge", "machine": mid, "grok_account": None}
    )
    assert bobreport.load_digest(home)["machines"][mid].get("grok_account") in (None, "")
    bobreport.apply_callback(
        home, {"op": "merge", "machine": mid, "grok_account": _FAKE_EMAIL}
    )
    bobreport.apply_callback(
        home, {"op": "merge", "machine": mid, "cleared": ["grok_account"]}
    )
    assert bobreport.load_digest(home)["machines"][mid].get("grok_account") in (None, "")


def test_fingerprint_changes_on_label(tmp_path: Path):
    home = _home(tmp_path)
    mid = "redqueen"
    bobreport.apply_callback(home, {"op": "merge", "machine": mid, "online": True})
    ent1 = bobreport.load_digest(home)["machines"][mid]
    fp1 = bobreport._machine_fingerprint(ent1)
    bobreport.apply_callback(
        home, {"op": "merge", "machine": mid, "grok_account": _FAKE_EMAIL}
    )
    ent2 = bobreport.load_digest(home)["machines"][mid]
    fp2 = bobreport._machine_fingerprint(ent2)
    assert fp1 != fp2
    fp3 = bobreport._machine_fingerprint(bobreport.load_digest(home)["machines"][mid])
    assert fp2 == fp3


def test_stale_peer_cannot_fill_or_clear_label(tmp_path: Path):
    home = _home(tmp_path)
    mid = "redqueen"
    bobreport.apply_callback(
        home, {"op": "merge", "machine": mid, "grok_account": _FAKE_EMAIL}
    )
    # Peer file without grok_account must not wipe chair export.
    import bobstat

    bobstat.write_peer(
        home,
        {"ok": True, "id": mid, "online": True, "weekly": 1, "cursor_label": "peer"},
    )
    ent = bobreport.load_digest(home)["machines"][mid]
    exported = bobreport.export_machine_for_tray(home, mid, ent)
    assert exported.get("grok_account") == _FAKE_EMAIL
    assert "grok_account" not in bobreport._MERGE_PEER_FIELDS


def test_publish_posts_label_only(monkeypatch):
    posted: list[dict] = []

    def fake_urlopen(req, timeout=0):  # noqa: ARG001
        body = json.loads(req.data.decode("utf-8"))
        posted.append(body)
        _scan_blob(body)
        _scan_blob(dict(req.headers))

        class Resp:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b""

        return Resp()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        code = bobreport.publish_grok_account_label(
            "redqueen", _FAKE_EMAIL, url="https://example.test/bob/v1/report"
        )
    assert code == 204
    assert posted[0]["op"] == "merge"
    assert posted[0]["machine"] == "redqueen"
    assert posted[0]["grok_account"] == _FAKE_EMAIL
    assert posted[0]["grok_account"] != "bob-redqueen"
    assert "online" not in posted[0]  # MRB #6167: label-only must not flip status
    assert "status" not in posted[0]
    assert "key" not in posted[0]
    assert "refresh_token" not in posted[0]


def test_ear_tick_publishes_and_retries(monkeypatch, tmp_path: Path):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(_auth_doc_email()), encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    posted: list[dict] = []
    codes = [503, 204]

    def fake_post(payload, *, url=None, timeout=15.0):  # noqa: ARG001
        posted.append(payload)
        _scan_blob(payload)
        return codes.pop(0) if codes else 204

    monkeypatch.setattr(bobreport, "post_report_json", fake_post)

    client = irc_agent.Client.__new__(irc_agent.Client)
    client.args = types.SimpleNamespace(chair=False)
    client.original_nick = "Bob-redqueen"
    client.home = tmp_path
    client._grok_account_last = 0.0
    client._grok_account_delivered = irc_agent._GROK_ACCOUNT_UNSET
    client._grok_account_chair = irc_agent._GROK_ACCOUNT_UNSET
    monkeypatch.setattr(client, "_local_machine_id", lambda: "redqueen")
    monkeypatch.setattr(bobreport, "digest_fuel_heartbeat_s", lambda: 0.0)

    logs: list[str] = []
    monkeypatch.setattr(irc_agent, "info", logs.append)

    client._maybe_publish_grok_account()
    assert any("publish failed" in m for m in logs)
    assert client._grok_account_delivered is irc_agent._GROK_ACCOUNT_UNSET
    assert len(posted) == 1

    client._grok_account_last = 0.0
    client._maybe_publish_grok_account()
    assert any("publish ok" in m for m in logs)
    assert client._grok_account_delivered == _FAKE_EMAIL
    assert len(posted) == 2

    # Unchanged + agreeing chair => no POST.
    n = len(posted)
    client._grok_account_chair = _FAKE_EMAIL
    client._grok_account_last = 0.0
    client._maybe_publish_grok_account()
    assert len(posted) == n


def test_ear_tick_unknown_skips_post(monkeypatch, tmp_path: Path):
    auth = tmp_path / "auth.json"
    auth.write_text("{bad", encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_AUTH_PATH", str(auth))
    posted: list = []
    monkeypatch.setattr(
        bobreport, "post_report_json", lambda *a, **k: posted.append(1) or 204
    )
    client = irc_agent.Client.__new__(irc_agent.Client)
    client.args = types.SimpleNamespace(chair=False)
    client.original_nick = "Bob-redqueen"
    client.home = tmp_path
    client._grok_account_last = 0.0
    client._grok_account_delivered = irc_agent._GROK_ACCOUNT_UNSET
    client._grok_account_chair = irc_agent._GROK_ACCOUNT_UNSET
    monkeypatch.setattr(client, "_local_machine_id", lambda: "redqueen")
    monkeypatch.setattr(bobreport, "digest_fuel_heartbeat_s", lambda: 0.0)
    monkeypatch.setattr(irc_agent, "info", lambda *_: None)
    client._maybe_publish_grok_account()
    assert posted == []


def test_get_export_label_not_bob_redqueen(tmp_path: Path):
    """Fixture label surfaces on export/GET shape and is not bob-redqueen."""
    home = _home(tmp_path, mids={"redqueen"})
    mid = "redqueen"
    bobreport.apply_callback(
        home,
        {"op": "merge", "machine": mid, "online": True, "grok_account": _FAKE_EMAIL},
    )
    doc = bobreport.load_digest(home)
    machines = {
        m: bobreport.export_machine_for_tray(home, m, e)
        for m, e in doc["machines"].items()
    }
    body = {"v": 1, "machines": machines}
    _scan_blob(body)
    label = body["machines"]["redqueen"].get("grok_account")
    assert label == _FAKE_EMAIL
    assert label != "bob-redqueen"
    assert "refresh_token" not in json.dumps(body)


def test_source_pins_ear_identity_out_of_peer_fields():
    src = Path(bobreport.__file__).read_text(encoding="utf-8")
    assert "_EAR_IDENTITY_FIELDS" in src
    assert "grok_account" in src
    assert "read_grok_account_label" in src
    assert "publish_grok_account_label" in src
    agent = Path(irc_agent.__file__).read_text(encoding="utf-8")
    assert "_maybe_publish_grok_account" in agent
    assert "grok account publish ok" in agent


def test_fr003_label_payload_omits_online():
    """MRB #6167: label merge must not send online (avoids status fingerprint churn)."""
    p = bobreport.build_grok_account_merge_payload("redqueen", _FAKE_EMAIL)
    assert p.get("grok_account") == _FAKE_EMAIL
    assert "online" not in p
    assert "status" not in p
    p2 = bobreport.build_grok_account_merge_payload("redqueen", None)
    assert p2.get("grok_account") is None
    assert "online" not in p2


def test_fr003_chair_mismatch_rate_limited(monkeypatch, tmp_path):
    """MRB #6167: after ok publish, chair=None mismatch must not POST every heartbeat."""
    import irc_agent

    posts = []

    def fake_publish(mid, label, **kw):
        posts.append((mid, label))
        return 204

    monkeypatch.setattr(bobreport, "publish_grok_account_label", fake_publish)
    monkeypatch.setattr(bobreport, "read_grok_account_label", lambda: ("ok", _FAKE_EMAIL))
    monkeypatch.setattr(bobreport, "digest_fuel_heartbeat_s", lambda: 1.0)

    class Args:
        chair = False

    client = irc_agent.Client.__new__(irc_agent.Client)
    client.args = Args()
    client.original_nick = "Bob-redqueen"
    client._local_machine_id = lambda: "redqueen"
    client._grok_account_last = 0.0
    client._grok_account_delivered = irc_agent._GROK_ACCOUNT_UNSET
    client._grok_account_chair = irc_agent._GROK_ACCOUNT_UNSET
    client._grok_account_chair_mismatch_last = 0.0

    # First publish
    client._maybe_publish_grok_account()
    assert len(posts) == 1
    assert client._grok_account_delivered == _FAKE_EMAIL

    # Simulate digest pull that still lacks grok_account
    client._grok_account_chair = None
    client._grok_account_last = 0.0
    client._maybe_publish_grok_account()
    # Within 600s chair-mismatch window: no second POST
    assert len(posts) == 1

    # After rate-limit window, allow one reconcile POST
    client._grok_account_chair_mismatch_last = 0.0
    client._grok_account_last = 0.0
    # pretend 601s ago
    client._grok_account_chair_mismatch_last = __import__("time").time() - 601.0
    client._maybe_publish_grok_account()
    assert len(posts) == 2
