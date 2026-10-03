"""Chair background jobs (FR t760u): 30-min webhook health probe + 15-min authenticated GitHub resync. All fakes."""
from __future__ import annotations

import json
from pathlib import Path

import bobcallback
import chair_health as ch
import gitclaim
from repo_layout import ROOT  # t773u: split repo; legacy flat paths resolve per service

BASES = {"local": "http://127.0.0.1:7700", "public": "https://irc.ntsa.uk"}
OK = {"/bob/v1/report": 200, "/bob/v1/jira": 200, "/bob/v1/intake/jeeves-health-probe": 404, "/bob/v1/git": 204}


class FakeHttp:
    def __init__(self):
        self.calls = []
        self.override = {}        # (target, path) -> status

    def __call__(self, method, url, body=None, headers=None, timeout=10.0):
        self.calls.append((method, url, body, headers or {}))
        for tname, base in BASES.items():
            if url.startswith(base):
                path = url[len(base):]
                return self.override.get((tname, path), OK[path])
        raise AssertionError(url)


def cycle(home, h, now):
    return ch.probe_cycle(home, now=now, http=h, sleep=lambda s: None, bases=BASES)


# ---------------------------------------------------------------- webhook health
def test_probe_all_up_no_announce_and_state_file(tmp_path):
    h = FakeHttp()
    out = cycle(tmp_path, h, 1000.0)
    assert out["announce"] == []
    assert all(" up " in ln for ln in out["log"]) and len(out["log"]) == 2
    st = json.loads((tmp_path / "webhook-health.json").read_text())
    assert st["targets"]["local"]["up"] and st["targets"]["public"]["up"]
    # checks: GET report, GET jira, GET intake/<id> (404 = up), synthetic git ping POST - on BOTH targets
    seen = {(m, u.split("://", 1)[1].split("/", 1)[0], u[u.index("/bob"):]) for m, u, _b, _h in h.calls}
    for host in ("127.0.0.1:7700", "irc.ntsa.uk"):
        assert ("GET", host, "/bob/v1/report") in seen
        assert ("GET", host, "/bob/v1/jira") in seen
        assert ("GET", host, "/bob/v1/intake/jeeves-health-probe") in seen
        assert ("POST", host, "/bob/v1/git") in seen
    post = [c for c in h.calls if c[0] == "POST"][0]
    assert post[3]["X-GitHub-Event"] == "ping"
    assert json.loads(post[2])["zen"] == ch.PROBE_ZEN


def test_announce_only_on_transitions(tmp_path):
    h = FakeHttp()
    assert cycle(tmp_path, h, 0)["announce"] == []
    h.override[("public", "/bob/v1/git")] = 502
    o = cycle(tmp_path, h, 1800)
    assert len(o["announce"]) == 1 and o["announce"][0].startswith("WEBHOOK DOWN public") and "git=502" in o["announce"][0]
    assert cycle(tmp_path, h, 3600)["announce"] == []          # still down: silent
    assert cycle(tmp_path, h, 5400)["announce"] == []
    h.override.clear()
    o = cycle(tmp_path, h, 7200)
    assert len(o["announce"]) == 1 and o["announce"][0].startswith("WEBHOOK RECOVERED public") and "after 1h30m" in o["announce"][0]
    assert cycle(tmp_path, h, 9000)["announce"] == []          # up again: silent


def test_local_down_connection_refused_counts_as_down(tmp_path):
    h = FakeHttp()
    cycle(tmp_path, h, 0)
    for p in OK:
        h.override[("local", p)] = 0
    o = cycle(tmp_path, h, 1800)
    assert [a for a in o["announce"] if "DOWN local" in a] and not [a for a in o["announce"] if "public" in a]


def test_single_blip_is_retried_and_not_announced(tmp_path):
    h = FakeHttp()
    cycle(tmp_path, h, 0)
    state = {"n": 0}
    real = h.__call__

    def flaky(method, url, body=None, headers=None, timeout=10.0):
        if url.endswith("/bob/v1/report") and url.startswith(BASES["local"]):
            state["n"] += 1
            if state["n"] == 1:
                return 0
        return real(method, url, body, headers, timeout)

    o = ch.probe_cycle(tmp_path, now=1800, http=flaky, sleep=lambda s: None, bases=BASES)
    assert o["announce"] == []


def test_intake_404_up_but_500_down_and_report_must_be_200(tmp_path):
    for path, code, down in (("/bob/v1/intake/jeeves-health-probe", 404, False),
                             ("/bob/v1/intake/jeeves-health-probe", 500, True),
                             ("/bob/v1/report", 404, True), ("/bob/v1/jira", 503, True)):
        h = FakeHttp()
        h.override[("local", path)] = code
        out = ch.probe_cycle(tmp_path / f"{abs(hash((path, code)))}", now=0, http=h, sleep=lambda s: None, bases=BASES) \
            if (tmp_path / f"{abs(hash((path, code)))}").mkdir() is None else None
        assert bool([a for a in out["announce"] if "DOWN local" in a]) is down


def test_first_run_down_announces_once(tmp_path):
    h = FakeHttp()
    for p in OK:
        h.override[("public", p)] = 0
    o = cycle(tmp_path, h, 0)
    assert len(o["announce"]) == 1 and "DOWN public" in o["announce"][0]
    assert cycle(tmp_path, h, 1800)["announce"] == []


def test_probe_ping_is_quiet_on_the_receiver(tmp_path):
    body = json.dumps({"zen": ch.PROBE_ZEN, "repository": {"full_name": ch.PROBE_REPO}}).encode()
    code, _ = bobcallback.handle_git_webhook({"X-GitHub-Event": "ping"}, body, tmp_path)
    assert code == 204
    assert not (tmp_path / "chair-outbox.txt").exists()            # nothing announced on #bobiverse
    assert gitclaim.load_unaccepted(tmp_path) == []
    # a real ping with another zen still announces; a non-owner repo is still refused (owner gate runs first)
    real = json.dumps({"zen": "Keep it logically awesome.", "repository": {"full_name": "SimonBarnett/x"}}).encode()
    assert bobcallback.handle_git_webhook({"X-GitHub-Event": "ping"}, real, tmp_path)[0] == 204
    assert (tmp_path / "chair-outbox.txt").exists()
    evil = json.dumps({"zen": ch.PROBE_ZEN, "repository": {"full_name": "evil/x"}}).encode()
    assert bobcallback.handle_git_webhook({"X-GitHub-Event": "ping"}, evil, tmp_path)[0] == 403


# ---------------------------------------------------------------- resync_from_github (merge, authenticated)
def fetcher(table, seen=None):
    def f(url):
        if seen is not None:
            seen.append(url)
        for k, v in table.items():
            if k in url:
                if isinstance(v, Exception):
                    raise v
                return v
        return []
    return f


def seed(home):
    doc = {"v": 1, "accepted": [{"repo": "o/a", "task": "FR", "id": "#9", "nick": "bob-x"}], "unaccepted": [
        {"repo": "o/a", "task": "FR", "id": "#1", "seq": 1, "line": "keep-me"},
        {"repo": "o/a", "task": "FR", "id": "#2", "seq": 2},                     # closed on GitHub -> dropped
        {"repo": "o/a", "task": "UAT", "id": "#3", "seq": 3},                    # other kind -> kept
        {"repo": "o/bad", "task": "FR", "id": "#4", "seq": 4},                   # fetch fails -> kept
        {"repo": "o/a", "task": "FR", "id": "#5", "seq": 5, "offered_to": "bob-y"},   # offered -> kept
    ]}
    gitclaim._write_queue(gitclaim.queue_path(home), doc)


def test_resync_merges_keeps_accepted_and_failed_repos(tmp_path):
    seed(tmp_path)
    table = {"o/a/issues": [{"number": 1}, {"number": 7}, {"number": 8, "pull_request": {"url": "x"}}, {"number": 9}],
             "o/a/pulls": [{"number": 8, "title": "x", "body": "closes #7"}],
             "o/bad/": RuntimeError("403")}
    res = gitclaim.resync_from_github(tmp_path, ["o/a", "o/bad"], fetch_json=fetcher(table), token="SECRET-TOKEN-123")
    assert res["ok"] and res["failed"] == ["o/bad"] and res["repos"] == ["o/a"]
    assert "SECRET-TOKEN-123" not in json.dumps(res)
    rows = {(r["repo"], r["task"], r["id"]): r for r in gitclaim.load_unaccepted(tmp_path)}
    assert ("o/a", "FR", "#1") in rows and rows[("o/a", "FR", "#1")]["line"] == "keep-me"
    # mrb-664-fix / FR #628: per-issue UAT rows are kept; only closed FR #2 is dropped here.
    assert ("o/a", "FR", "#2") not in rows and res["dropped"] == 1
    assert ("o/a", "UAT", "#3") in rows and ("o/bad", "FR", "#4") in rows and ("o/a", "FR", "#5") in rows
    assert ("o/a", "MRB", "#8") in rows
    assert ("o/a", "FR", "#7") not in rows                    # superseded by the closing PR
    assert ("o/a", "FR", "#9") not in rows                    # already accepted by a bob: not re-offered
    assert [a["id"] for a in gitclaim.load_accepted(tmp_path)] == ["#9"]


def test_resync_skips_ignored_repos(tmp_path):
    seen = []
    res = gitclaim.resync_from_github(tmp_path, ["o/a", "o/b"], fetch_json=fetcher({"o/b/issues": [{"number": 1}]}, seen),
                                      ignored=["o/a"])
    assert res["repos"] == ["o/b"] and not [u for u in seen if "/o/a/" in u]


# ---------------------------------------------------------------- ChairJobs scheduling
class Clock:
    def __init__(self): self.t = 10_000.0
    def __call__(self): return self.t


def make_jobs(tmp_path, clock, http, token=("TOK-VALUE", "file:C:\\ai\\jeeves\\config\\github.token"), table=None):
    logs, ann = [], []
    seen = []
    j = ch.ChairJobs(tmp_path, tmp_path, log=logs.append, announce=ann.append, http=http,
                     fetch_json=fetcher(table or {}, seen), token_loader=lambda: token,
                     ignored_loader=lambda: [], clock=clock, sleep=lambda s: None, spawn=False, owners={"o"})
    return j, logs, ann, seen


def test_jobs_schedule_probe_30m_resync_15m(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", "o/a")
    clk = Clock()
    h = FakeHttp()
    monkeypatch.setattr(ch, "targets", lambda: BASES)
    j, logs, ann, seen = make_jobs(tmp_path, clk, h, table={"o/a/issues": [{"number": 1}]})
    assert j.tick() is False                       # nothing due at t0
    probes = lambda: len([c for c in h.calls if c[1].endswith("/bob/v1/report") and "127" in c[1]])
    clk.t += ch.FIRST_PROBE_DELAY_S + 1
    assert j.tick() is True and probes() == 1
    clk.t += ch.FIRST_RESYNC_DELAY_S
    assert j.tick() is True and j.last_resync["ok"]
    n_resync = len([u for u in seen if "/issues" in u])
    clk.t += 600
    j.tick(); assert len([u for u in seen if "/issues" in u]) == n_resync          # <15 min: nothing
    clk.t += 400
    j.tick(); assert len([u for u in seen if "/issues" in u]) == 2 * n_resync        # 15 min later
    clk.t += 1000
    j.tick(); assert probes() == 2                                                  # 30 min after the first probe
    assert [u for u in logs if "webhook-health" in u] and [u for u in logs if "github-resync ok" in u]


def test_token_source_logged_once_to_file_and_value_never(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", "o/a")
    monkeypatch.setattr(ch, "targets", lambda: BASES)
    clk = Clock()
    j, logs, ann, seen = make_jobs(tmp_path, clk, FakeHttp())
    for _ in range(3):
        clk.t += ch.RESYNC_S + 1
        j.request_resync(); j.tick()
    f = (tmp_path / ch.TOKEN_SOURCE_LOG).read_text()
    assert f.count("resync token source: file:") == 1
    assert "TOK-VALUE" not in f and "TOK-VALUE" not in "\n".join(logs)
    assert len([ln for ln in logs if "token source" in ln]) == 1


def test_no_token_skips_resync_without_wiping(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", "o/a")
    monkeypatch.setattr(ch, "targets", lambda: BASES)
    seed(tmp_path)
    clk = Clock()
    j, logs, ann, seen = make_jobs(tmp_path, clk, FakeHttp(), token=("", "none"))
    clk.t += ch.RESYNC_S; j.tick()
    assert seen == [] and j.last_resync["error"] == "no token"
    assert len(gitclaim.load_unaccepted(tmp_path)) == 5
    assert "resync token source: none" in (tmp_path / ch.TOKEN_SOURCE_LOG).read_text()


def test_jobs_announce_via_chair_outbox_on_transition(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "targets", lambda: BASES)
    clk = Clock(); h = FakeHttp()
    j = ch.ChairJobs(tmp_path, tmp_path, log=lambda s: None, http=h, token_loader=lambda: ("", "none"),
                     clock=clk, sleep=lambda s: None, spawn=False)
    clk.t += 100; j.tick()
    h.override[("local", "/bob/v1/git")] = 500
    clk.t += ch.WEBHOOK_PROBE_S + 1; j.tick()
    clk.t += ch.WEBHOOK_PROBE_S + 1; j.tick()
    lines = (tmp_path / "chair-outbox.txt").read_text().splitlines()
    assert len(lines) == 1 and lines[0].startswith("PRIVMSG #bobiverse :WEBHOOK DOWN local")


def test_discover_prefers_config_then_queue_and_token_repos(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_RESYNC_REPOS", raising=False)
    seed(tmp_path)
    getter = fetcher({"/user/repos": [{"full_name": "o/new", "has_issues": True},
                                       {"full_name": "o/old", "archived": True},
                                       {"full_name": "other/x"}]})
    got = ch.discover_repos(tmp_path, {"o"}, getter, ignored=["o/bad"])
    assert "o/new" in got and "o/a" in got and "o/old" not in got and "other/x" not in got and "o/bad" not in got
    (tmp_path / "resync-repos.txt").write_text("# list\no/only\n")
    assert ch.discover_repos(tmp_path, {"o"}, getter, ignored=[]) == ["o/only"]


def test_iis_rewrite_has_public_digest_rule():
    txt = (ROOT / "scripts" / "Install-BobWebhooks.ps1").read_text(encoding="utf-8-sig")
    assert 'bob/v1/digest$' in txt and "BobDigestWebhook" in txt
    assert txt.count("BobDigestWebhook") >= 3        # fresh config, rules table, and the existing-config insert

