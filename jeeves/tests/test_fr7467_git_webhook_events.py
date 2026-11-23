"""FR #7467: /bob/v1/git accepts all 8 subscribed events; HMAC; reason bodies; 503."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from pathlib import Path

import pytest

import bobcallback
import bobreport
import gitclaim
import intake
import webhook_queue

ALLOW = {"127.0.0.1"}
FAKE_SECRET = "FAKE_git_webhook_hmac_test_secret_7467"
SUBSCRIBED = (
    "check_run",
    "check_suite",
    "issues",
    "issue_comment",
    "pull_request",
    "pull_request_review",
    "push",
    "workflow_run",
)


def _owner_repo(prefix: str = "acme") -> tuple[str, str]:
    owner = f"{prefix}{uuid.uuid4().hex[:8]}"
    name = f"widget-{uuid.uuid4().hex[:6]}"
    return owner, f"{owner}/{name}"


def _sign(body: bytes, secret: str = FAKE_SECRET) -> str:
    dig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={dig}"


def _post(home, obj, *, event: str, headers=None, rate=None, raw=None, secret=None, sign=False, bad_sig=None):
    body = raw if raw is not None else json.dumps(obj, separators=(",", ":")).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "X-GitHub-Event": event}
    if headers:
        hdrs.update(headers)
    if sign or secret is not None or bad_sig is not None:
        if bad_sig is not None:
            hdrs["X-Hub-Signature-256"] = bad_sig
        else:
            hdrs["X-Hub-Signature-256"] = _sign(body, secret or FAKE_SECRET)
    bobcallback.pop_response_headers()
    return bobcallback.handle_request(
        "POST",
        "/bob/v1/git",
        hdrs,
        body,
        "127.0.0.1",
        home,
        ALLOW,
        filer=intake.FakeGitHubFiler(),
        report_rate=rate,
    )


def _err(body: bytes) -> str:
    doc = json.loads(body.decode("utf-8"))
    assert doc.get("ok") is False
    return str(doc.get("error") or "")


def _payload(event: str, full_name: str) -> dict:
    repo = {"full_name": full_name}
    if event == "push":
        return {"ref": "refs/heads/main", "repository": repo, "commits": [], "after": "a" * 40}
    if event == "issues":
        return {
            "action": "opened",
            "repository": repo,
            "issue": {"number": 1, "title": "t", "state": "open", "labels": []},
        }
    if event == "issue_comment":
        return {
            "action": "created",
            "repository": repo,
            "issue": {"number": 2, "title": "t", "state": "open", "pull_request": {}},
            "comment": {"body": "ok", "user": {"login": "alice"}},
        }
    if event == "pull_request":
        return {
            "action": "opened",
            "repository": repo,
            "pull_request": {
                "number": 3,
                "title": "pr",
                "state": "open",
                "merged": False,
                "draft": False,
                "html_url": f"https://github.com/{full_name}/pull/3",
                "labels": [],
            },
        }
    if event == "pull_request_review":
        return {
            "action": "submitted",
            "repository": repo,
            "pull_request": {
                "number": 4,
                "html_url": f"https://github.com/{full_name}/pull/4",
                "head": {"sha": "b" * 40},
            },
            "review": {"state": "approved", "body": "lgtm", "user": {"login": "alice"}},
        }
    if event == "check_run":
        return {
            "action": "completed",
            "repository": repo,
            "check_run": {
                "name": "ci",
                "status": "completed",
                "conclusion": "success",
                "head_sha": "c" * 40,
                "pull_requests": [],
            },
        }
    if event == "check_suite":
        return {
            "action": "completed",
            "repository": repo,
            "check_suite": {
                "status": "completed",
                "conclusion": "success",
                "head_sha": "d" * 40,
            },
        }
    if event == "workflow_run":
        return {
            "action": "completed",
            "repository": repo,
            "workflow_run": {
                "id": 99,
                "status": "completed",
                "conclusion": "success",
                "head_sha": "e" * 40,
                "html_url": "https://example.invalid/wf",
            },
        }
    raise AssertionError(event)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_GIT_WEBHOOK_SECRET_FILE", raising=False)
    monkeypatch.delenv("BOB_GIT_ALLOW_UNSIGNED", raising=False)
    monkeypatch.delenv("BOB_CONFIG_DIR", raising=False)
    return tmp_path


@pytest.fixture()
def signed_home(tmp_path, monkeypatch):
    owner, _ = _owner_repo("own")
    monkeypatch.setenv("BOB_GIT_OWNERS", owner)
    sec = tmp_path / "FAKE_github-webhook.secret"
    sec.write_text(FAKE_SECRET + "\n", encoding="utf-8")
    monkeypatch.setenv("BOB_GIT_WEBHOOK_SECRET_FILE", str(sec))
    monkeypatch.delenv("BOB_GIT_ALLOW_UNSIGNED", raising=False)
    return tmp_path, owner


def test_fr7467_all_eight_signed_return_2xx(signed_home):
    home, owner = signed_home
    for event in SUBSCRIBED:
        _, full = _owner_repo(owner[:4] if False else "")
        # keep owner allow-list: rebuild full under fixture owner
        full = f"{owner}/repo-{event.replace('_', '')[:8]}-{uuid.uuid4().hex[:4]}"
        code, body = _post(home, _payload(event, full), event=event, sign=True)
        assert 200 <= code < 300, (event, code, body)
        assert FAKE_SECRET.encode() not in body
        assert b"sha256=" not in body


def test_fr7467_invalid_signature_401_reason(signed_home):
    home, owner = signed_home
    full = f"{owner}/sig-bad"
    obj = _payload("push", full)
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    cases = [
        ("sha256=" + ("0" * 64), "invalid signature"),
        ("sha1=dead", "invalid signature"),
        ("", "missing signature"),
    ]
    for bad, want in cases:
        if bad == "":
            code, resp = _post(home, obj, event="push", headers={"X-GitHub-Delivery": "d1"})
            # missing header
            assert code == 401, resp
            assert _err(resp) == "missing signature"
        else:
            code, resp = _post(home, obj, event="push", bad_sig=bad)
            assert code == 401
            assert _err(resp) == want
        pending = list((home / "webhook-queue" / "pending").glob("*.json")) if (home / "webhook-queue").exists() else []
        # also check common queue layout
        pending += list(home.rglob("wh_*.json"))
        for p in pending:
            raw = p.read_bytes()
            assert FAKE_SECRET.encode() not in raw
            assert b"x-hub-signature" not in raw.lower()


def test_fr7467_altered_body_invalid_sig(signed_home):
    home, owner = signed_home
    full = f"{owner}/altered"
    obj = _payload("issues", full)
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    sig = _sign(body)
    tampered = body[:-1] + (b"X" if body[-1:] != b"X" else b"Y")
    code, resp = _post(home, None, event="issues", raw=tampered, bad_sig=sig)
    assert code == 401
    assert _err(resp) == "invalid signature"


def test_fr7467_workflow_run_and_unknown_204_no_enqueue(signed_home, capsys):
    home, owner = signed_home
    full = f"{owner}/ignore-me"
    before = {p.resolve() for p in home.rglob("*.json")}
    for event in ("workflow_run", "delete", "fork"):
        code, body = _post(home, _payload("workflow_run", full) if event == "workflow_run" else {
            "action": "deleted",
            "repository": {"full_name": full},
            "ref": "refs/heads/x",
        }, event=event, sign=True)
        assert code == 204, (event, body)
        assert body == b""
    after = {p.resolve() for p in home.rglob("*.json")}
    # no new pending envelopes for ignored events
    new = after - before
    for p in new:
        text = p.read_text(encoding="utf-8")
        assert '"kind": "git"' not in text or '"state": "pending"' not in text
    out = capsys.readouterr().out.lower()
    assert "workflow_run" in out or "ignored" in out


def test_fr7467_pull_request_review_not_400(signed_home):
    home, owner = signed_home
    full = f"{owner}/review-ok"
    code, body = _post(home, _payload("pull_request_review", full), event="pull_request_review", sign=True)
    assert code != 400
    assert 200 <= code < 300


def test_fr7467_4xx_reason_vocabulary(signed_home, monkeypatch):
    home, owner = signed_home
    full = f"{owner}/reasons"
    code, body = _post(home, {"repository": {"full_name": full}}, event="", sign=True, headers={"X-GitHub-Event": ""})
    # empty event header: force missing
    bobcallback.pop_response_headers()
    code, body = bobcallback.handle_request(
        "POST",
        "/bob/v1/git",
        {"Content-Type": "application/json", "X-Hub-Signature-256": _sign(b"{}")},
        b"{}",
        "127.0.0.1",
        home,
        ALLOW,
    )
    assert code == 400
    assert _err(body) == "missing event header"

    raw = b"{"
    code, body = _post(home, None, event="push", raw=raw, sign=True)
    assert code == 400
    assert _err(body) == "malformed JSON"

    raw = b"[1,2]"
    code, body = _post(home, None, event="push", raw=raw, sign=True)
    assert code == 400
    assert _err(body) == "payload must be a JSON object"

    code, body = _post(home, {"zen": "x"}, event="ping", sign=True)
    assert code == 400
    assert _err(body) == "missing repository"

    code, body = _post(
        home,
        {"ref": "refs/heads/main", "repository": {"full_name": "otherowner/x"}, "commits": []},
        event="push",
        sign=True,
    )
    assert code == 403
    assert _err(body) == "owner not allowed"

    big = b"x" * (bobcallback.MAX_BODY_BYTES + 2)
    code, body = _post(home, None, event="push", raw=big, sign=True)
    assert code == 413
    assert _err(body) == "body too large"

    rate = intake.RateLimiter(per_min=1)
    ok = _payload("push", full)
    assert _post(home, ok, event="push", sign=True, rate=rate)[0] in (200, 204)
    code, body = _post(home, ok, event="push", sign=True, rate=rate)
    assert code == 429
    assert _err(body) == "rate limited"


def test_fr9104_check_run_check_suite_rate_deferred_204(signed_home):
    """FR #9104: under local rate limit, CI storms ack 204; push still 429."""
    home, owner = signed_home
    full = f"{owner}/rate-defer"
    rate = intake.RateLimiter(per_min=1)
    # Burn the bucket with a successful push.
    assert _post(home, _payload("push", full), event="push", sign=True, rate=rate)[0] in (
        200,
        204,
    )
    for event in ("check_run", "check_suite"):
        code, body = _post(
            home, _payload(event, full), event=event, sign=True, rate=rate
        )
        assert code == 204, (event, code, body)
        assert body == b""
    code, body = _post(home, _payload("push", full), event="push", sign=True, rate=rate)
    assert code == 429
    assert _err(body) == "rate limited"
    code, body = _post(
        home, _payload("pull_request", full), event="pull_request", sign=True, rate=rate
    )
    assert code == 429
    assert _err(body) == "rate limited"


def test_fr7467_processing_deferred_503(signed_home, monkeypatch):
    home, owner = signed_home
    full = f"{owner}/defer"
    monkeypatch.setattr(
        bobreport,
        "apply_git_webhook",
        lambda *a, **k: bobreport.GitWebhookOutcome(ok=False, err="outbox"),
    )
    code, body = _post(home, _payload("push", full), event="push", sign=True)
    assert code == 503
    doc = json.loads(body.decode("utf-8"))
    assert doc.get("error") == "processing deferred"
    extra = dict(bobcallback.pop_response_headers())
    assert "Retry-After" in {k for k in extra} or any(k.lower() == "retry-after" for k in extra)

    def boom(*a, **k):
        raise RuntimeError("injected")

    monkeypatch.setattr(bobreport, "apply_git_webhook", boom)
    code, body = _post(home, _payload("issues", full), event="issues", sign=True)
    assert code == 503
    assert json.loads(body.decode("utf-8")).get("error") == "processing deferred"


def test_fr7467_no_secret_unsigned_still_works(home, monkeypatch):
    owner, full = _owner_repo("unsigned")
    monkeypatch.setenv("BOB_GIT_OWNERS", owner)
    code, _ = _post(home, _payload("push", full), event="push")
    assert code in (200, 204)
    code, _ = _post(home, _payload("pull_request_review", full), event="pull_request_review")
    assert code in (200, 204)
    code, _ = _post(home, _payload("workflow_run", full), event="workflow_run")
    assert code == 204


def test_fr7467_allow_unsigned_missing_only(signed_home, monkeypatch):
    home, owner = signed_home
    monkeypatch.setenv("BOB_GIT_ALLOW_UNSIGNED", "1")
    full = f"{owner}/allow-miss"
    code, _ = _post(home, _payload("push", full), event="push")
    assert code in (200, 204)
    code, body = _post(home, _payload("push", full), event="push", bad_sig="sha256=" + ("ab" * 32))
    assert code == 401
    assert _err(body) == "invalid signature"


def test_fr7467_announce_outcome_is_204(signed_home, monkeypatch):
    home, owner = signed_home
    full = f"{owner}/announce"
    monkeypatch.setattr(
        bobreport,
        "apply_git_webhook",
        lambda *a, **k: bobreport.GitWebhookOutcome(ok=False, err="announce"),
    )
    code, body = _post(home, _payload("push", full), event="push", sign=True)
    assert code == 204
    assert body == b""


def test_fr7467_generic_repos_parametrized_over_two_owners(signed_home):
    home, owner_a = signed_home
    owner_b = f"org{uuid.uuid4().hex[:8]}"
    import os

    os.environ["BOB_GIT_OWNERS"] = f"{owner_a},{owner_b}"
    for owner in (owner_a, owner_b):
        full = f"{owner}/multi-{uuid.uuid4().hex[:4]}"
        code, _ = _post(home, _payload("push", full), event="push", sign=True)
        assert code in (200, 204)
