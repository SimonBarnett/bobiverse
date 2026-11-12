"""FR #6758 / FR-10: appliance doc matches https://jeeves.ntsa.uk/ and groups."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves" / "docs" / "jeeves-settings-appliance.md"

EIGHT_GROUPS = (
    "Fuel and review waits",
    "Digest",
    "IRC timing",
    "Chair home",
    "Wake and ticket closure",
    "Webhook probes",
    "Resync",
    "Secrets",
)


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_fr6758_https_url_no_browse_7701():
    text = _doc()
    assert "https://jeeves.ntsa.uk/" in text
    assert "Browse `http://jeeves.ntsa.uk:7701/" not in text
    assert "Browse `http://127.0.0.1:7701/" not in text


def test_fr6758_internal_dns_and_public_host_refusal():
    text = _doc()
    low = text.lower()
    assert "internal dns" in low
    assert "bob.ntsa.uk" in text
    assert "irc.ntsa.uk" in text
    assert "do **not** front it via `bob.ntsa.uk`" in low or (
        "bob.ntsa.uk" in text and "irc.ntsa.uk" in text and "never" in low
    )


def test_fr6758_operator_supplied_cert_no_public_dns_instruction():
    text = _doc()
    low = text.lower()
    assert "operator-supplied" in low or "operator supplied" in low
    assert "certificate" in low
    # Refusal is allowed; a positive "create public DNS" step is not.
    for line in text.splitlines():
        stripped = line.strip().lower()
        if "public dns" not in stripped:
            continue
        assert "not" in stripped, stripped


def test_fr6758_eight_groups_defaults_checkboxes_queue_pools():
    text = _doc()
    for title in EIGHT_GROUPS:
        assert title in text, title
    low = text.lower()
    assert "checkbox" in low
    assert "default" in low
    assert "settings page" in low or "settings table" in low
    assert "`/queue`" in text or "GET /queue" in text
    assert "`/pools`" in text or "GET /pools" in text
    assert "copilot" in low
    assert "overspend" in low
    assert "percent" in low or "percents" in low
