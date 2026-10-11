"""MRB #4093: airc shell latency / needs_human profiling lives in airc-troubleshooting (not harvest)."""
from __future__ import annotations

from repo_layout import ROOT

SKILL = ROOT / "airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md"
HARVEST = ROOT / "common/.grok/skills/harvest/SKILL.md"


def _utf8(p):
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {p}"
    return raw.decode("utf-8")


def test_mrb4093_airc_shell_latency_needs_human_in_troubleshooting():
    t = _utf8(SKILL)
    assert "needs_human" in t
    assert "Slow remote shell" in t or "latency" in t.lower()
    assert "IRC" in t and ("timings" in t.lower() or "timing" in t.lower())
    harvest = _utf8(HARVEST)
    assert "Live airc shell latency differences across fleet boxes are needs_human" not in harvest
