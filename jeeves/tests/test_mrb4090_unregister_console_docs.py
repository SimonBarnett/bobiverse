"""MRB #4090 hostile: FR #4040 console list docs sit on !unregister (not !register)."""
from __future__ import annotations

from repo_layout import ROOT

DOCS = ROOT / "jeeves/docs/jeeves-commands.md"
SKILL = ROOT / "jeeves/.grok/skills/bobiverse-jeeves-commands/SKILL.md"


def _utf8(p):
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {p}"
    return raw.decode("utf-8")


def test_mrb4090_unregister_docs_carry_console_list_not_register():
    docs = _utf8(DOCS)
    # Find the primary command table unregister row.
    unreg = [ln for ln in docs.splitlines() if ln.startswith("| `!unregister <#channel|machine>")]
    assert unreg, "unregister table row missing"
    assert "FR #4040" in unreg[0] or "*_console" in unreg[0] or "console" in unreg[0].lower()
    reg = [ln for ln in docs.splitlines() if ln.startswith("| `!register <#channel|machine>` | `ACK registered")]
    assert reg, "register ACK table row missing"
    assert "4040" not in reg[0]
    assert "*_console" not in reg[0]


def test_mrb4090_jeeves_commands_skill_mentions_4040_console_list():
    skill = _utf8(SKILL)
    assert "FR #4008 / #4040" in skill or ("!unregister" in skill and "4040" in skill)
    assert "*_console" in skill or "console" in skill.lower()
