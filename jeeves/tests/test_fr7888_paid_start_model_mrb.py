"""FR #7888: MRB eligibility follows the launched start_model."""
from __future__ import annotations

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    registered_machines.save_registered(tmp_path, {"redqueen", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-11-16T10:00:{seq:02d}Z",
        "line": "x",
    }
    if task == "MRB":
        r["url"] = f"https://github.com/{repo}/pull/{num}"
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []})


def _seed(home, mid, pid, **fields):
    doc = bobreport.empty_digest()
    doc["machines"][mid] = bobreport._empty_machine(mid)
    nick = f"{mid}-{pid}"
    worker = {"state": "idle", "nick": nick, "kind": "opencode"}
    worker.update(fields)
    doc["machines"][mid]["workers"] = {pid: worker}
    listed = {
        "nick": nick,
        "state": "idle",
        "work": "",
        "updated": "2026-11-16T12:00:00Z",
        "kind": worker.get("kind") or "opencode",
    }
    listed.update(fields)
    doc["machines"][mid]["worker_list"] = [listed]
    bobreport.save_digest(home, doc)
    return nick


def test_paid_start_model_gets_mrb_when_configured_is_free(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    notes = []
    monkeypatch.setattr(gitclaim, "_log_queue_purge", lambda msg, log=None: notes.append(msg))
    _queue(home, [_row("SimonBarnett/bobiverse", "MRB", 7870, 1)])
    fi.handle_focus_cmd(home, "hi bobiverse")
    nick = _seed(
        home,
        "redqueen",
        "8580",
        start_model="opencode-go/deepseek-v4-pro",
        configured_model="opencode/deepseek-v4.1-flash-free",
        model_mismatch=True,
        cost_tier="min",
    )
    st, job = gitclaim.offer_focus_top(home, nick, "#redqueen")
    assert st == "ok"
    assert job is not None
    assert str(job.get("task")).upper() == "MRB"
    assert "paid start_model" in str(job.get("mrb_eligibility"))
    assert any("mrb-eligibility offer" in n and "paid start_model" in n for n in notes)


def test_free_start_model_never_gets_mrb(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    notes = []
    monkeypatch.setattr(gitclaim, "_log_queue_purge", lambda msg, log=None: notes.append(msg))
    _queue(
        home,
        [
            _row("SimonBarnett/bobiverse", "MRB", 7870, 1),
            _row("SimonBarnett/bobiverse", "FR", 7888, 2),
        ],
    )
    fi.handle_focus_cmd(home, "hi bobiverse")
    nick = _seed(
        home,
        "redqueen",
        "1",
        kind="grok",
        start_model="opencode/deepseek-v4.1-flash-free",
        configured_model="opencode-go/deepseek-v4-pro",
        cost_tier="max",
    )
    st, job = gitclaim.offer_focus_top(home, nick, "#redqueen")
    assert st == "ok"
    assert job is not None
    assert str(job.get("task")).upper() == "FR"
    assert any("free start_model" in n for n in notes)


def test_unknown_and_dollar_start_model_are_free(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, [_row("SimonBarnett/bobiverse", "MRB", 7870, 1)])
    fi.handle_focus_cmd(home, "hi bobiverse")
    nick = _seed(home, "redqueen", "2", start_model="$model", configured_model="opencode-go/deepseek-v4-pro")
    st, job = gitclaim.offer_focus_top(home, nick, "#redqueen")
    assert job is None or str((job or {}).get("task")).upper() != "MRB"
    assert st != "ok" or job is None
    nick2 = _seed(home, "redqueen", "3", start_model="", configured_model="opencode-go/deepseek-v4-pro")
    st2, job2 = gitclaim.offer_focus_top(home, nick2, "#redqueen")
    assert job2 is None or str((job2 or {}).get("task")).upper() != "MRB"


def test_author_seat_is_not_offered_its_mrb(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    notes = []
    monkeypatch.setattr(gitclaim, "_log_queue_purge", lambda msg, log=None: notes.append(msg))
    nick = _seed(
        home,
        "redqueen",
        "8580",
        start_model="opencode-go/deepseek-v4-pro",
        configured_model="opencode/deepseek-v4.1-flash-free",
        model_mismatch=True,
        cost_tier="min",
    )
    _queue(
        home,
        [_row("SimonBarnett/bobiverse", "MRB", 7870, 1, author_seat=nick)],
    )
    fi.handle_focus_cmd(home, "hi bobiverse")
    st, job = gitclaim.offer_focus_top(home, nick, "#redqueen")
    assert job is None or str((job or {}).get("task")).upper() != "MRB"
    assert any("reason=author" in n and nick in n for n in notes)
    assert st != "ok" or job is None


def test_assign_refuses_free_and_allows_paid(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _queue(home, [_row("SimonBarnett/bobiverse", "MRB", 7870, 1)])
    free_nick = _seed(home, "marchhare", "9", start_model="opencode/deepseek-v4.1-flash-free")
    st, detail = gitclaim.assign_row(home, free_nick, "SimonBarnett/bobiverse", "MRB", "7870")
    assert st == "refused"
    assert "7888" in str(detail) or "free" in str(detail).lower()
    paid = _seed(
        home,
        "redqueen",
        "8580",
        start_model="opencode-go/deepseek-v4-pro",
        configured_model="opencode/deepseek-v4.1-flash-free",
        model_mismatch=True,
        cost_tier="min",
    )
    st2, detail2 = gitclaim.assign_row(home, paid, "SimonBarnett/bobiverse", "MRB", "7870")
    assert st2 == "ok"
    assert str((detail2 or {}).get("task") or "").upper() == "MRB"
