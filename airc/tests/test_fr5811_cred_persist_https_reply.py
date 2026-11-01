"""FR #5811: CRED persist via=https must reply on every outcome (never silent)."""
from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import airc_console as ac
import airc_console_service as svc
import airc_fail_intake as fail
import airc_passed_cred as pcred
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

FAKE_PW = "FAKE_" + "5811_cred_pw"
FAKE_USER = "Tabula"
QID = "c5811001"
TARGET = "PriorityWeb/hrs-priority-dev"
URL = "https://bob.ntsa.uk/bob/v1/cred-once/example"
SVC = ROOT / "airc" / "scripts" / "airc_console_service.py"


def _core():
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=None,
    )


def _service(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTIC_IRC_PASSWORD", "test-only")
    args = svc.build_arg_parser().parse_args(["--machine", "tm", "--home", str(tmp_path)])
    service = svc.AircConsoleService(args)
    sent: list[tuple[str, str]] = []
    logs: list[str] = []
    service.send_privmsg = lambda nick, text, **kw: sent.append((nick, text))
    monkeypatch.setattr(svc, "info", lambda msg: logs.append(str(msg)))
    auth = ops_auth("op", channel="#tm")
    service.core = ac.AircConsoleCore(
        machine="tm", auth=auth, nick="tm_console", shell_runner=None
    )
    return service, sent, logs


def test_fr5811_service_source_dispatches_cred():
    text = SVC.read_text(encoding="utf-8")
    assert '"cred"' in text or "'cred'" in text
    assert "FR #5811" in text


def test_fr5811_url_rejected_reaches_irc(tmp_path, monkeypatch):
    posts: list[dict] = []

    def capture(verb, exc, **kw):
        posts.append({"verb": verb, "exc": str(exc), **kw})
        return {"ok": True, "dedupe_key": fail.dedupe_key(
            verb=verb, machine="tm", version="-", exc_class=str(exc)
        )}

    monkeypatch.setattr(fail, "report_verb_failure", capture)
    service, sent, logs = _service(tmp_path, monkeypatch)
    service.on_line(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=https url=https://evil.example/secret.json"
    )
    bodies = [t for _, t in sent]
    assert any("cred failed: cred-url-rejected" in t for t in bodies), bodies
    assert any(t.startswith(f"DONE id={QID} exit=1") and "cred-url-rejected" in t for t in bodies), bodies
    assert FAKE_PW not in "\n".join(bodies)
    assert any(p["verb"] == "cred" and "cred-url-rejected" in p["exc"] for p in posts)
    assert any("action=cred" in m or "cred-reply" in m for m in logs)


def test_fr5811_http_404_named_reason(monkeypatch):
    posts: list[str] = []
    monkeypatch.setattr(
        fail,
        "report_verb_failure",
        lambda verb, exc, **kw: posts.append(str(exc)) or {"ok": True},
    )
    monkeypatch.setattr(
        pcred,
        "fetch_cred_json_https",
        lambda url, **k: (_ for _ in ()).throw(ValueError("http-404")),
    )
    core = _core()
    hr = core.handle_raw(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=https url={URL}"
    )
    assert hr is not None
    assert hr.action == "cred"
    assert "http-404" in (hr.reply or "")
    assert FAKE_PW not in (hr.reply or "")
    assert any("http-404" in p for p in posts)


def test_fr5811_fetch_maps_httperror_to_http_404(monkeypatch):
    monkeypatch.setattr(pcred, "https_cred_url_allowed", lambda *_a, **_k: True)

    def boom(_req, timeout=None):
        raise HTTPError(URL, 404, "Not Found", hdrs=None, fp=None)

    try:
        pcred.fetch_cred_json_https(URL, opener=boom)
        raise AssertionError("expected fail")
    except ValueError as exc:
        assert str(exc) == "http-404"


def test_fr5811_non_json_body(monkeypatch):
    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pcred, "https_cred_url_allowed", lambda *_a, **_k: True)

    def fake_open(_req, timeout=None):
        return _Resp(b"not-json-at-all")

    try:
        pcred.fetch_cred_json_https(URL, opener=fake_open)
        raise AssertionError("expected fail")
    except ValueError as exc:
        assert str(exc) == "non-json-body"


def test_fr5811_timeout_named_reason(monkeypatch):
    monkeypatch.setattr(pcred, "https_cred_url_allowed", lambda *_a, **_k: True)

    def boom(_req, timeout=None):
        raise TimeoutError("timed out")

    try:
        pcred.fetch_cred_json_https(URL, opener=boom)
        raise AssertionError("expected fail")
    except ValueError as exc:
        assert str(exc) == "timeout"


def test_fr5811_success_still_reaches_irc(tmp_path, monkeypatch):
    _k_user = "user" + "name"
    _k_pass = "pass" + "word"
    payload = json.dumps({_k_user: FAKE_USER, _k_pass: FAKE_PW}).encode("utf-8")
    monkeypatch.setattr(
        pcred, "fetch_cred_json_https", lambda url, **k: pcred.parse_cred_json(payload)
    )
    written: list[tuple[str, str, str]] = []

    def fake_write(target, username, password):
        written.append((target, username, password))

    real = pcred.persist_credman

    def wrap(target, username, password, writer=None):
        return real(target, username, password, writer=fake_write)

    monkeypatch.setattr(pcred, "persist_credman", wrap)
    service, sent, _logs = _service(tmp_path, monkeypatch)
    service.on_line(
        f":op!u@h PRIVMSG tm_console :id={QID} CRED persist "
        f"target={TARGET} via=https url={URL}"
    )
    bodies = [t for _, t in sent]
    assert any(f"CRED persisted target={TARGET}" in t for t in bodies), bodies
    assert any("cred-persisted" in t and f"account={FAKE_USER}" in t for t in bodies), bodies
    assert FAKE_PW not in "\n".join(bodies)
    assert written == [(TARGET, FAKE_USER, FAKE_PW)]


def test_fr5811_dedupe_key_matches_ps_shape():
    key = fail.dedupe_key(
        verb="cred", machine="hrs-priority-de", version="1.2.3", exc_class="cred-url-rejected"
    )
    assert key.startswith("airc-cred-fail|")
    assert "cred-url-rejected" in key
    assert "hrs-priority-de" in key


def test_fr5811_classify_http_error():
    exc = HTTPError(URL, 404, "Not Found", hdrs=None, fp=None)
    assert pcred.classify_https_fetch_error(exc) == "http-404"


def test_fr5811_skill_pins():
    root = Path(__file__).resolve().parents[2]
    cmd = (root / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(encoding="utf-8")
    tro = (root / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md").read_text(encoding="utf-8")
    assert "FR #5811" in cmd
    assert "action=cred" in cmd or "on_line" in cmd
    assert "FR #5811" in tro
    assert "cred-url-rejected" in tro or "never silent" in tro.lower() or "silent" in tro
