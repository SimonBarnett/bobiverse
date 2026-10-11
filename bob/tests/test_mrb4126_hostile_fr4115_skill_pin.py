"""docs/mrb-4126: pin bobiverse-bob-worker skill documents FR #4115 inject recovery."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"


def test_mrb4126_skill_pins_fr4115_inject_recovery():
    raw = SKILL.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    text = raw.decode("utf-8")
    assert "FR #4115" in text
    assert "clipboard readback" in text.lower() or "read back" in text.lower()
    assert "inject failed" in text
    assert "BOB_WORKER_CLIPBOARD_RESTORE_S" in text or "delayed restore" in text.lower() or "only if" in text
    assert "BOB_WORKER_STARTUP_READY_CAP_S" in text or "wait-ready" in text.lower()
    # Enter-only still applies inside the verify loop
    assert "Enter only" in text