"""Harvest #10102: Digest #10078 promotes public Bob skill MCP + seat HTTPS loader."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEAT = ROOT / "bob/agents/worker/.grok/skills/bobiverse-worker-seat/SKILL.md"
WORKER_LESSONS = ROOT / "bob/.grok/skills/bobiverse-bob-worker/lessons.md"
AGENTS = ROOT / "bob/agents/worker/AGENTS.md"
LOG = ROOT / "common/docs/skill-harvest-log.md"
HOME = ROOT / "jeeves/www/irc-ntsa/index.html"


def test_fr10102_worker_seat_public_mcp():
    text = SEAT.read_text(encoding="utf-8")
    assert "FR #10102" in text
    assert "plan.ntsa.uk" in text
    assert "list_catalog" in text and "get_skill" in text
    assert "https://bob.ntsa.uk/mcp" in text
    assert "Do not" in text and "`git clone`" in text


def test_fr10102_worker_lessons_and_agents():
    lessons = WORKER_LESSONS.read_text(encoding="utf-8")
    assert "FR #10102" in lessons
    assert "#10092" in lessons
    agents = AGENTS.read_text(encoding="utf-8")
    assert "https://bob.ntsa.uk/mcp" in agents
    assert "Do not `git clone`" in agents


def test_fr10102_skill_harvest_log():
    text = LOG.read_text(encoding="utf-8")
    assert "10102" in text
    assert "Digest #10078" in text
    assert "list_catalog" in text
    assert "<<<<<<" not in text


def test_fr10102_product_stack_pins_still_present():
    assert (ROOT / "common/tests/test_fr10080_bob_mcp.py").is_file()
    assert (ROOT / "common/tests/test_fr10081_seat_loads_mcp_skill.py").is_file()
    home = HOME.read_text(encoding="utf-8")
    assert "POST /mcp" in home
    assert "list_catalog" in home


def test_fr10102_files_end_with_newline():
    for p in (SEAT, WORKER_LESSONS, LOG, Path(__file__)):
        assert p.read_bytes().endswith(b"\n"), p
