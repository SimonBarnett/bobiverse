"""FR #8477: promote aged draft skill leaflets; keep DONE receipts as drafts."""
from __future__ import annotations

import sys
from pathlib import Path

import gitclaim

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))
import skill_promote_backlog as spb  # noqa: E402

REPO = "o/a"
LABELS = [{"name": "via-intake"}, {"name": "skill"}]
SKILL_FILE = [".grok/skills/example-book/SKILL.md"]


def _pr(n, title, body, *, draft=True, created="2020-01-01T00:00:00Z"):
    return {
        "number": n,
        "title": title,
        "body": body,
        "html_url": f"https://github.com/o/a/pull/{n}",
        "state": "open",
        "draft": draft,
        "labels": LABELS,
        "files": SKILL_FILE,
        "created_at": created,
        "user": {"login": "intake"},
        "head": {"ref": f"harvest-{n}"},
        "base": {"ref": "main"},
    }


def _fetch(table):
    def fetch(url: str):
        if "/issues" in url and "/pulls" not in url:
            return table.get("issues", [])
        if "/pulls" in url and "/files" not in url and "state=closed" not in url:
            return table.get("pulls", [])
        return []

    return fetch


def test_receipt_title_is_not_a_leaflet():
    assert gitclaim.is_draft_skill_leaflet(
        title="skill: DONE FR o/a#1",
        body="Lesson\nreal steps",
        labels=["via-intake", "skill"],
        files=SKILL_FILE,
    ) is False


def test_resync_skips_draft_receipt_even_with_promote(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    called = []
    pr = _pr(11, "skill: DONE FR o/a#1", "Lesson\nsteps")

    def promote(repo, blob):
        called.append(blob.get("number"))
        return gitclaim.promoted_draft_skill_view(blob)

    gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch({"pulls": [pr], "issues": []}),
        promote_draft_skill=promote,
    )
    assert called == []
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(r.get("id") == "#11" for r in rows)


def test_leaflet_stays_draft_without_promote(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    pr = _pr(
        12,
        "skill: SaaS checkout retry",
        "Target skill book: `example-book`\n\nWrite the retry once.",
    )
    gitclaim.resync_from_github(
        tmp_path, [REPO], fetch_json=_fetch({"pulls": [pr], "issues": []})
    )
    rows = gitclaim.load_unaccepted(tmp_path)
    assert not any(r.get("id") == "#12" for r in rows)


def test_promoted_leaflet_queues_mrb_with_lesson_title(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    pr = _pr(
        13,
        "skill: SaaS checkout retry",
        "Target skill book: `example-book`\n\nWrite the retry once.",
    )

    def promote(repo, blob):
        assert repo == REPO
        return gitclaim.promoted_draft_skill_view(blob)

    gitclaim.resync_from_github(
        tmp_path,
        [REPO],
        fetch_json=_fetch({"pulls": [pr], "issues": []}),
        promote_draft_skill=promote,
    )
    rows = [
        r
        for r in gitclaim.load_unaccepted(tmp_path)
        if r.get("task") == "MRB" and r.get("id") == "#13"
    ]
    assert len(rows) == 1
    assert "lesson(example-book):" in str(rows[0].get("title") or rows[0].get("line") or "")


def test_aged_leaflets_ignore_receipts_and_young_drafts():
    old = _pr(21, "skill: real leaflet", "A real procedure body.")
    receipt = _pr(22, "skill: PASS MRB o/a#2", "A real procedure body.")
    young = _pr(
        23,
        "skill: real leaflet",
        "A real procedure body.",
        created="2099-01-01T00:00:00Z",
    )
    now = 1_700_000_000.0
    aged = spb.aged_draft_skill_leaflets(
        [old, receipt, young], now=now, max_age_s=6 * 3600
    )
    assert [p["number"] for p in aged] == [21]


def test_github_promote_needs_token_and_node():
    assert gitclaim.github_promote_draft_skill_leaflet("o/a", {"number": 1}, token="") is None
    assert (
        gitclaim.github_promote_draft_skill_leaflet(
            "o/a", {"number": 1, "node_id": "PR_1"}, token=""
        )
        is None
    )


def test_monitor_exit_finding_on_aged_leaflet(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "FAKE_TOKEN")
    monkeypatch.setenv("BOB_DRAFT_SKILL_PROMOTE_AGE_H", "6")
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    digest.mkdir()
    (digest / "queue.json").write_text(
        '{"v":1,"unaccepted":[],"accepted":[],"done":[]}', encoding="utf-8"
    )
    old = _pr(31, "skill: real leaflet", "A real procedure body.")

    def fetch(repo, token):
        assert token == "FAKE_TOKEN"
        return [], [old]

    monkeypatch.setattr(spb, "_fetch_open_lists", fetch)
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()
    payload, code = spb.check(args)
    assert code == spb.EXIT_FINDING
    assert any("draft_skill_unpromoted" in f for f in payload["findings"])
