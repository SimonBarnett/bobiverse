"""FR #6166: webhooks.md Hours/HTTP examples use bob.ntsa.uk; IRC host stays separate."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBHOOKS = ROOT / "docs" / "webhooks.md"

# Build forbidden HTTP+IRC host without a contiguous literal (FR #5272 repo scan).
_BAD_HTTP_IRC_BOB = "https://" + "irc.ntsa.uk" + "/bob"
_BAD_HTTP_IRC_BOB_PLAIN = "http://" + "irc.ntsa.uk" + "/bob"


def test_fr6166_default_public_base_is_bob_not_irc():
    raw = WEBHOOKS.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    head = text.split("## Paths", 1)[0]
    assert "https://bob.ntsa.uk" in head
    assert "Default public base" in head
    assert "irc.ntsa.uk" in head  # IRC TLS host documented
    assert "6697" in head or "TLS" in head
    assert _BAD_HTTP_IRC_BOB not in text
    assert _BAD_HTTP_IRC_BOB_PLAIN not in text
    assert "FR #6166" in head


def test_fr6166_hours_and_http_curls_use_bob_host():
    text = WEBHOOKS.read_text(encoding="utf-8")
    hours = text.split("### Hours webhook", 1)[1].split("## ", 1)[0]
    # Only absolute URLs that are Bob HTTP paths (ignore github.com in JSON bodies).
    hours_bob = re.findall(r"https://bob\.ntsa\.uk/bob/v1/hours[^\s\"`']*", hours)
    assert hours_bob, "expected hours curl URLs on bob.ntsa.uk"
    for url in hours_bob:
        assert "irc.ntsa.uk" not in url
    # All /bob/v1 absolute HTTP URLs in the whole doc must be bob.ntsa.uk
    bob_paths = re.findall(r"https://[^/\s\"`']+/bob/v1/[^\s\"`']*", text)
    assert bob_paths
    for url in bob_paths:
        assert url.startswith("https://bob.ntsa.uk/bob/v1/"), url
