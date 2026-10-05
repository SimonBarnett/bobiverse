"""FR #2419: FR DONE must not carry PASS/FAIL; grammar strips them and keeps the PR url."""
from __future__ import annotations

from pathlib import Path

import shop_listen
from repo_layout import ROOT

SHOP = ROOT / "common/scripts/shop_listen.py"
WORKER = ROOT / "bob/scripts/bob_worker.py"
SKILL = ROOT / "bob/.grok/skills/bobiverse-bob-job-irc/SKILL.md"
THIS = Path(__file__)
MOJIBAKE_DASH = ("\u00e2" + "\u20ac")

PR_URL = "https://github.com/SimonBarnett/bobiverse/pull/2417"


def test_fr2419_parse_strips_pass_on_fr_done():
    p = shop_listen.parse_shop_job_line(
        f"DONE FR SimonBarnett/bobiverse#2413 PASS {PR_URL}"
    )
    assert p is not None
    assert p.verb == "DONE" and p.task == "FR" and p.id == "#2413"
    assert p.result.upper() != "PASS"
    assert p.url == PR_URL
    assert "/pull/" in (p.url or p.result)


def test_fr2419_parse_strips_pass_merged_on_fr_done():
    p = shop_listen.parse_shop_job_line(
        f"DONE FR SimonBarnett/bobiverse#2413 PASS merged {PR_URL}"
    )
    assert p is not None
    assert p.url == PR_URL
    assert p.result.upper() != "PASS" and "PASS" not in p.result.upper()


def test_fr2419_parse_fr_done_url_only():
    p = shop_listen.parse_shop_job_line(
        f"DONE FR SimonBarnett/bobiverse#2413 {PR_URL}"
    )
    assert p is not None
    assert p.url == PR_URL
    assert p.result == PR_URL or "/pull/" in p.result


def test_fr2419_mrb_pass_unchanged():
    p = shop_listen.parse_shop_job_line(
        f"DONE MRB SimonBarnett/bobiverse#2417 PASS {PR_URL}"
    )
    assert p is not None
    assert p.task == "MRB"
    assert p.result == "PASS"
    assert p.url == PR_URL


def test_fr2419_complete_fr_done_pass_clears_accepted(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    import gitclaim

    doc = {
        "unaccepted": [],
        "accepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "id": "#2413",
                "task": "FR",
                "nick": "win-mpre8vi4u6u-7764",
                "title": "demo",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    parsed = shop_listen.parse_shop_job_line(
        f"DONE FR SimonBarnett/bobiverse#2413 PASS {PR_URL}"
    )
    assert parsed is not None
    st, job = shop_listen.complete_job_by_ref(
        home,
        nick="win-mpre8vi4u6u-7764",
        repo=parsed.repo,
        task=parsed.task,
        ident=parsed.id,
        result=parsed.result,
        url=parsed.url,
    )
    assert st == "ok"
    assert job is not None
    assert job.get("url") == PR_URL or "/pull/" in str(job.get("result") or "")
    after = gitclaim._load_queue_unlocked(home)
    assert after.get("accepted") == []
    assert any(str(r.get("id")) == "#2413" for r in (after.get("done") or []))


def test_fr2419_docs_and_prompt():
    skill = SKILL.read_text(encoding="utf-8")
    assert "2419" in skill
    assert "FR never carries PASS/FAIL" in skill or "no PASS/FAIL" in skill
    shop = SHOP.read_text(encoding="utf-8")
    assert "2419" in shop
    prompt = WORKER.read_text(encoding="utf-8")
    assert "no PASS/FAIL" in prompt and "2419" in prompt


def test_fr2419_encoding():
    for path in (SHOP, THIS):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert raw.endswith(b"\n")
        if path != THIS:
            assert MOJIBAKE_DASH not in raw.decode("utf-8")
