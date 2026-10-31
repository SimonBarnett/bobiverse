"""FR #5316: Copilot out-of-tokens pauses dispatch for 7 days."""
from __future__ import annotations

import json

import copilot_dispatch as cd
import gitclaim
import shop_listen

REPO = "SimonBarnett/bobiverse"
NOW = 1_700_000_000.0


def _row(num=10):
    return {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": "do the thing",
    }


def test_fr5316_no_tokens_sets_seven_day_cooldown(tmp_path):
    cd.set_allowance(tmp_path, remaining=3)
    posts: list = []

    def post(*_a, **_k):
        posts.append(1)
        return {"status": 403, "message": "out of tokens"}

    out = cd.dispatch_row(tmp_path, _row(), post=post, now=NOW)
    assert out["status"] == "exhausted"
    assert cd.is_exhausted({"status": 403, "message": "out of tokens"})
    assert cd.cooldown_active(tmp_path, now=NOW)
    until = cd.load_allowance(tmp_path).get("exhausted_until")
    assert until == NOW + cd.COPILOT_COOLDOWN_S
    assert until == NOW + 7 * 86400
    assert not cd.has_allowance(tmp_path, now=NOW)
    # no further dispatch / no probing
    again = cd.dispatch_row(tmp_path, _row(11), post=post, now=NOW + 60)
    assert again["status"] == "exhausted"
    assert len(posts) == 1


def test_fr5316_releases_held_copilot_rows(tmp_path):
    gitclaim.apply_queue_event(
        tmp_path,
        gitclaim.GitClaim(
            repo=REPO, task="FR", id="#22", event="issues", action="opened", line="x"
        ),
    )
    shop_listen.accept_job_by_ref(
        tmp_path,
        nick="copilot",
        channel="#bobiverse",
        repo=REPO,
        task="FR",
        ident="#22",
        title="t",
    )
    assert any(
        str(r.get("nick") or "") == "copilot" for r in gitclaim.load_accepted(tmp_path)
    )
    announced: list[str] = []
    cd.mark_tokens_exhausted(
        tmp_path, fuel="copilot", now=NOW, announce=announced.append
    )
    acc = gitclaim.load_accepted(tmp_path)
    assert not any(str(r.get("nick") or "") == "copilot" for r in acc)
    un = gitclaim.load_unaccepted(tmp_path)
    row = next(r for r in un if r.get("id") == "#22")
    assert str(row.get("nick") or "") != "copilot"
    assert "copilot" not in str(row.get("giveup_seats") or "").lower()
    assert announced
    assert "paused until" in announced[0].lower()
    assert "copilot out of tokens" in announced[0].lower()


def test_fr5316_cooldown_survives_reload(tmp_path):
    cd.mark_tokens_exhausted(tmp_path, now=NOW)
    p = tmp_path / cd.ALLOWANCE_NAME
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["exhausted_until"] == NOW + 7 * 86400
    assert cd.cooldown_active(tmp_path, now=NOW + 100)
    assert not cd.has_allowance(tmp_path, now=NOW + 100)
    # after 7 days, cooldown lifts; dispatch still requires allowance/enabled
    assert not cd.cooldown_active(tmp_path, now=NOW + 7 * 86400 + 1)
    cd.set_allowance(tmp_path, remaining=2)
    assert cd.has_allowance(tmp_path, now=NOW + 7 * 86400 + 1)


def test_fr5316_digest_shows_resume(tmp_path):
    cd.mark_tokens_exhausted(tmp_path, now=NOW)
    pool = cd.pool_for_digest(tmp_path)
    assert pool["state"] == "exhausted"
    assert pool.get("resume_at")
    assert "T" in str(pool["resume_at"])


def test_fr5316_tick_skips_fetch_while_cooled(tmp_path):
    cd.mark_tokens_exhausted(tmp_path, now=NOW)
    fetches = []

    def fetch():
        fetches.append(1)
        return {"quota_snapshots": {"premium_interactions": {"unlimited": True}}}

    posts = []
    cd.tick(
        tmp_path,
        now=NOW + 10,
        fetch_user=fetch,
        post=lambda *_a, **_k: posts.append(1) or {"status": 201, "id": "t1"},
    )
    assert fetches == []
    assert posts == []
