"""FR #4970: customer-specific harvest lessons go to priority-customer repos."""
from __future__ import annotations

import logging
from pathlib import Path

import intake
import priority_customer as pc

ROOT = Path(__file__).resolve().parents[2]
JOB_MRB = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
HARVEST_AS = ROOT / "common" / ".grok" / "skills" / "harvest-agent-skills" / "SKILL.md"
WORKER = ROOT / "bob" / "agents" / "worker" / ".grok" / "skills" / "bobiverse-worker-seat" / "SKILL.md"

# Fake topic set includes a newly tagged name (not a hardcoded customer).
FAKE_TOPICS = frozenset(
    {
        "simonbarnett/rees",
        "simonbarnett/trutex",
        "simonbarnett/euroflo",
        "simonbarnett/ce-priority",
        "simonbarnett/acme-widgets",
    }
)


def _utf8(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    return raw.decode("utf-8")


def test_fr4970_mrb_skill_has_customer_repo_redirect():
    text = _utf8(JOB_MRB)
    section = text[text.index("## Harvest-lesson intake PRs") : text.index("## Skill / markdown")]
    assert "priority-customer" in section
    assert "SimonBarnett/rees" in section
    assert "SimonBarnett/agentic_fomprep" in section
    assert "would this be true for every Priority customer" in section
    assert "MOVED" in section
    assert "must not merge" in section.lower() or "do not merge" in section.lower()


def test_fr4970_honesty_box_states_customer_vs_general():
    for path in (HARVEST, HARVEST_AS, WORKER):
        text = _utf8(path)
        assert "priority-customer" in text, path
        assert "SimonBarnett/rees" in text, path
        assert "SimonBarnett/agentic_fomprep" in text, path
        assert "every Priority customer" in text, path


def test_fr4970_rees_lesson_routes_to_rees_not_fomprep():
    own = intake.lesson_owner_repo(
        title="harvest: Rees Machinery Priority instance forms",
        body="Lessons:\n- Rees Priority data mapping for this customer only\n",
        topic_repos=FAKE_TOPICS,
    )
    assert own.repo == "SimonBarnett/rees"
    assert own.missing is False


def test_fr4970_new_tagged_customer_via_fake_topic_set():
    own = intake.lesson_owner_repo(
        title="harvest: Acme-widgets Priority forms",
        body="Customer-specific Priority instance for acme-widgets.\n",
        topic_repos=FAKE_TOPICS,
    )
    assert own.repo == "SimonBarnett/acme-widgets"


def test_fr4970_general_priority_still_fomprep():
    own = intake.lesson_owner_repo(
        title="harvest: Priority catalog cat-t12",
        body="Lessons:\n- agentic_fomprep form-prep true for any customer\n",
        topic_repos=FAKE_TOPICS,
    )
    assert own.repo == "SimonBarnett/agentic_fomprep"


def test_fr4970_resolve_skill_book_customer_not_fomprep_or_bobiverse_harvest():
    book, path = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: Rees Priority forms",
        body="customer-specific",
        repo="SimonBarnett/rees",
        topic_repos=FAKE_TOPICS,
    )
    assert book == "harvest-agent-skills"
    assert path.replace("\\", "/") == ".grok/skills/harvest-agent-skills/SKILL.md"
    assert "common/.grok/skills/harvest" not in path.replace("\\", "/")

    book2, path2 = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: Acme-widgets",
        body="new tagged customer",
        repo="SimonBarnett/acme-widgets",
        topic_repos=FAKE_TOPICS,
    )
    assert book2 == "harvest-agent-skills"
    assert "agentic_fomprep" not in path2


def test_fr4970_ce_priority_still_dayworks_launcher():
    book, path = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: tip",
        body="x",
        repo="SimonBarnett/ce-priority",
        topic_repos=FAKE_TOPICS,
    )
    assert book == "dayworks-launcher"
    assert path.replace("\\", "/") == "dayworks/.grok/skills/dayworks-launcher/SKILL.md"


def test_fr4970_lookup_fail_keeps_last_set_never_drops(tmp_path, caplog):
    pc.save_topic_repos(tmp_path, ["SimonBarnett/rees"])

    def boom(_url):
        raise TimeoutError("gh down")

    caplog.set_level(logging.WARNING)
    kept = pc.refresh_topic_repos(tmp_path, fetch_json=boom)
    assert "simonbarnett/rees" in kept
    assert any("priority-customer" in r.message for r in caplog.records)
    own = intake.lesson_owner_repo(
        title="harvest: Rees Priority instance",
        body="customer forms",
        topic_repos=kept,
    )
    assert own.repo == "SimonBarnett/rees"
