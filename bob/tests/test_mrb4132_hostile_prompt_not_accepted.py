"""docs/mrb-4132: pin PromptNotAcceptedWatcher skill + opt-out."""
from pathlib import Path
import importlib.util
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
SCRIPTS = ROOT / "bob" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _bw():
    spec = importlib.util.spec_from_file_location("bob_worker", SCRIPTS / "bob_worker.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mrb4132_skill_pins_prompt_not_accepted():
    raw = SKILL.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    assert "PromptNotAcceptedWatcher" in text
    assert "BOB_WORKER_PROMPT_RETRY" in text
    assert "prompt-not-accepted" in text
    assert "inject failed" in text
    # Inject paste header pin must stay intact (extra FR ids may already be in header on main)
    assert "* **Inject paste (FR #2498 / #1601" in text


def test_prompt_retry_enabled_optout(monkeypatch):
    bw = _bw()
    monkeypatch.delenv("BOB_WORKER_PROMPT_RETRY", raising=False)
    assert bw._prompt_retry_enabled() is True
    for v in ("0", "false", "no", "off", "FALSE"):
        monkeypatch.setenv("BOB_WORKER_PROMPT_RETRY", v)
        assert bw._prompt_retry_enabled() is False, v
    monkeypatch.setenv("BOB_WORKER_PROMPT_RETRY", "1")
    assert bw._prompt_retry_enabled() is True
