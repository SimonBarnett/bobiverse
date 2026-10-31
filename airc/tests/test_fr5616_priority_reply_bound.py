"""FR #5616: PRIORITY out lines stay within IRC_SAFE_PAYLOAD / PRIORITY_REPLY_MAX_BYTES."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_priority as ap


def _allowlist(tmp_path: Path, *, ids: list[str] | None = None) -> Path:
    rows = []
    for i in ids or ["dev1"]:
        rows.append(
            {
                "id": i,
                "url": "https://example.invalid/priority",
                "company": "live1",
                "user": "u1",
                "credentialTarget": f"PriorityWeb/{i}",
            }
        )
    path = tmp_path / "priority-instances.json"
    path.write_text(json.dumps({"instances": rows}), encoding="utf-8")
    return path


def _out_and_done(text: str) -> tuple[str, str]:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    assert len(lines) >= 2, text
    assert lines[-1].startswith("DONE ")
    return lines[0], lines[-1]


def test_fr5616_budget_matches_irc_safe_payload():
    assert ap.PRIORITY_REPLY_MAX_BYTES == ac.IRC_SAFE_PAYLOAD == 350


def test_fr5616_status_300_a_unknown_instance_bounded(tmp_path: Path):
    path = _allowlist(tmp_path)
    huge = "A" * 300
    r = ap.run_priority_verb("status", huge, job_id="00a5fd97", allowlist_path=path)
    assert not r.ok
    out, done = _out_and_done(r.reply_text())
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    assert out.startswith("out id=00a5fd97 seq=1 ")
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("ok") is False
    assert "unknown instance" in str(body.get("error") or "").lower()
    assert str(body.get("id") or "").endswith("...")
    assert done == "DONE id=00a5fd97 exit=1"


def test_fr5616_connect_multibyte_and_escape_tokens(tmp_path: Path):
    path = _allowlist(tmp_path)
    for token in ("€" * 300, "😀" * 200, 'x"\\y' * 80):
        r = ap.run_priority_verb(
            "connect", token, job_id="aabb0001", allowlist_path=path
        )
        out, done = _out_and_done(r.reply_text())
        assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
        body = json.loads(out.split("seq=1 ", 1)[1])
        assert "unknown instance" in str(body.get("error") or "").lower()
        assert str(body.get("id") or "").endswith("...")
        assert done == "DONE id=aabb0001 exit=1"


def test_fr5616_short_token_unchanged(tmp_path: Path):
    path = _allowlist(tmp_path)
    r = ap.run_priority_verb(
        "status", "../../etc", job_id="short001", allowlist_path=path
    )
    out, done = _out_and_done(r.reply_text())
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("id") == "../../etc"
    assert "unknown instance id: ../../etc" in str(body.get("error") or "")
    assert "..." not in str(body.get("id") or "")
    assert done == "DONE id=short001 exit=1"


def test_fr5616_all_ids_overflow_reply_too_large(tmp_path: Path):
    # Many long ids so status list JSON blows the framed-line budget.
    ids = [f"inst-{i:04d}-{'Z' * 40}" for i in range(40)]
    path = _allowlist(tmp_path, ids=ids)
    r = ap.run_priority_verb("status", None, job_id="list0001", allowlist_path=path)
    out, done = _out_and_done(r.reply_text())
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("ok") is False
    assert body.get("error") == "reply-too-large"
    assert body.get("action") == "status"
    assert isinstance(body.get("bytes"), int) and body["bytes"] > ap.PRIORITY_REPLY_MAX_BYTES
    assert done == "DONE id=list0001 exit=1"


def test_fr5616_in_budget_connect_byte_identical(tmp_path: Path):
    path = _allowlist(tmp_path)
    r = ap.run_priority_verb(
        "connect",
        "dev1",
        job_id="aabbccdd",
        allowlist_path=path,
        cred_fetcher=lambda _t: "FAKE_PRIORITY_PASSWORD_FOR_TEST",
        connector=ap.mock_connect,
    )
    text = r.reply_text()
    out, done = _out_and_done(text)
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    assert done == "DONE id=aabbccdd exit=0"
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body["ok"] is True
    assert "password" not in text.lower()


def test_fr5616_prepare_oversized_uses_shared_helper(tmp_path: Path):
    """Prepare path must not character-slice JSON mid-document."""
    from airc_auth_helpers import ops_auth
    from unittest.mock import MagicMock

    huge_reason = "R" * 500

    def fake_run(name, instance_id="", instances=None, **hooks):
        return {
            "ok": False,
            "reason": huge_reason,
            "ename": name,
            "sql_faked": False,
            "detail": "x" * 200,
        }

    class _PW:
        run_priority_prepare = staticmethod(fake_run)

    auth = ops_auth("bob-marchhare", channel="#marchhare")
    core = ac.AircConsoleCore(
        machine="marchhare",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="marchhare_console",
        job_protocol=MagicMock(),
        install_root=str(tmp_path),
    )
    import airc_console as ac_mod

    old = ac_mod._load_priority_worker
    ac_mod._load_priority_worker = lambda: _PW()
    try:
        r = core.handle_raw(
            ":bob-marchhare!u@h PRIVMSG marchhare_console "
            ":id=aabb0001 PRIORITY prepare HUGE"
        )
    finally:
        ac_mod._load_priority_worker = old
    assert r and r.action == "priority"
    out, done = _out_and_done(r.reply or "")
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("ok") is False
    assert body.get("error") == "reply-too-large"
    assert done == "DONE id=aabb0001 exit=1"


def test_fr5616_walk_oversized_bounded(tmp_path: Path):
    path = _allowlist(tmp_path)
    # Force an oversized walk payload via a custom fixture with a huge title.
    fix = tmp_path / "form_walk.json"
    fix.write_text(
        json.dumps(
            {
                "forms": {
                    "BIG": {
                        "title": "T" * 800,
                        "subforms": {},
                        "rows": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    wr = ap.run_priority_walk(
        text="id=aabb0002 PRIORITY formStart instance=dev1 form=BIG",
        allowlist_path=path,
        fixture_path=fix,
    )
    assert wr.lines
    out, done = wr.lines[0], wr.lines[-1]
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("ok") is False
    assert body.get("error") == "reply-too-large"
    assert done == "DONE id=aabb0002 exit=1"
